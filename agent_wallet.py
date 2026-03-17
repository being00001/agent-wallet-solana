"""
Agent Wallet Tool for Solana — Enhanced for Grant Proof

Provides unified wallet operations for autonomous agents on Solana:
- SOL + SPL token balances
- Transaction history (recent signatures + parsed tx details)
- Jupiter swap stub (quote + simulated execute)
- RPC failover with retry across multiple endpoints
- Multi-network support (mainnet, devnet, testnet)

Usage:
    from agent_wallet import agent_wallet_status, get_transaction_history
    from agent_wallet import jupiter_quote, jupiter_swap
    status = agent_wallet_status()
    history = get_transaction_history()
    quote = jupiter_quote("SOL", "USDC", 1.0)
    swap = jupiter_swap("SOL", "USDC", 1.0)
"""

import json
import time
import subprocess
from dataclasses import dataclass, field, asdict
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


# ── Default wallet ──────────────────────────────────────────────────────────
DEFAULT_WALLET = "3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb"

# ── SPL token mints ─────────────────────────────────────────────────────────
KNOWN_TOKENS_MAINNET = {
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
    "2b1kV6DkPAnxd5ixfnxCpjxmKwqjjaYmCZfHsFu24GXo": "PYUSD",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": "USDT",
}
KNOWN_TOKENS_DEVNET = {
    "CXk2AMBfi3TwaEL2468s6zP8xq9NxTXjp9gjMgzeUynM": "UNKNOWN_SPL",
}

# ── Jupiter token mints (mainnet) ──────────────────────────────────────────
JUPITER_MINTS = {
    "SOL": "So11111111111111111111111111111111111111112",
    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
}

# ── RPC endpoints with failover order ───────────────────────────────────────
RPC_ENDPOINTS = {
    "mainnet": [
        "https://api.mainnet-beta.solana.com",
        "https://solana-mainnet.rpc.extrnode.com",
        "https://rpc.ankr.com/solana",
    ],
    "devnet": [
        "https://api.devnet.solana.com",
    ],
    "testnet": [
        "https://api.testnet.solana.com",
    ],
}

# Legacy compat
NETWORK_URLS = {k: v[0] for k, v in RPC_ENDPOINTS.items()}

MAX_RPC_RETRIES = 3
RPC_TIMEOUT = 15


# ── Data classes ────────────────────────────────────────────────────────────

@dataclass
class TokenBalance:
    mint: str
    symbol: str
    balance: float


@dataclass
class TransactionInfo:
    signature: str
    slot: int
    block_time: Optional[int]
    success: bool
    fee: int  # lamports
    memo: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class JupiterQuote:
    input_mint: str
    output_mint: str
    input_amount: float
    output_amount: float
    price_impact_pct: float
    route_plan: str
    timestamp: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class JupiterSwapResult:
    success: bool
    input_mint: str
    output_mint: str
    input_amount: float
    output_amount: float
    tx_signature: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class WalletStatus:
    wallet: str
    network: str
    sol_balance: float
    tokens: list = field(default_factory=list)
    is_active: bool = True
    error: Optional[str] = None
    rpc_endpoint_used: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["tokens"] = [asdict(t) if isinstance(t, TokenBalance) else t for t in self.tokens]
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def summary(self) -> str:
        lines = [
            f"Wallet: {self.wallet}",
            f"Network: {self.network}",
            f"SOL: {self.sol_balance}",
        ]
        for t in self.tokens:
            tb = t if isinstance(t, TokenBalance) else TokenBalance(**t)
            lines.append(f"{tb.symbol}: {tb.balance}")
        if self.rpc_endpoint_used:
            lines.append(f"RPC: {self.rpc_endpoint_used}")
        if self.error:
            lines.append(f"Error: {self.error}")
        return "\n".join(lines)


# ── RPC with failover ──────────────────────────────────────────────────────

class RPCError(Exception):
    """Raised when all RPC endpoints fail."""
    pass


def rpc_call(method: str, params: list, network: str = "mainnet",
             timeout: int = RPC_TIMEOUT) -> dict:
    """
    Make a JSON-RPC call with failover across multiple endpoints.
    Retries up to MAX_RPC_RETRIES times, rotating through endpoints.
    """
    endpoints = RPC_ENDPOINTS.get(network, RPC_ENDPOINTS["mainnet"])
    last_error = None

    for attempt in range(MAX_RPC_RETRIES):
        endpoint = endpoints[attempt % len(endpoints)]
        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }).encode()

        req = Request(endpoint, data=payload,
                      headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode())
                if "error" in data:
                    last_error = data["error"]
                    continue
                return data
        except (URLError, HTTPError, TimeoutError, OSError) as e:
            last_error = str(e)
            continue

    raise RPCError(f"All RPC attempts failed after {MAX_RPC_RETRIES} retries. "
                   f"Last error: {last_error}")


def rpc_call_safe(method: str, params: list, network: str = "mainnet",
                  timeout: int = RPC_TIMEOUT) -> tuple[Optional[dict], Optional[str]]:
    """Safe wrapper that returns (result, error) instead of raising."""
    try:
        data = rpc_call(method, params, network, timeout)
        return data, None
    except RPCError as e:
        return None, str(e)


# ── CLI helpers ─────────────────────────────────────────────────────────────

def _run_cmd(args: list[str], timeout: int = 30) -> tuple[str, int]:
    """Run a CLI command and return (stdout, returncode)."""
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "timeout", 1
    except FileNotFoundError:
        return "command_not_found", 1


# ── Balance functions ───────────────────────────────────────────────────────

def read_wallet_balance_rpc(wallet: str, network: str = "mainnet") -> tuple[float, Optional[str]]:
    """Read SOL balance via JSON-RPC with failover. Returns (balance, endpoint_used)."""
    data, err = rpc_call_safe("getBalance", [wallet], network)
    if err:
        return -1.0, None
    try:
        lamports = data["result"]["value"]
        return lamports / 1e9, None
    except (KeyError, TypeError):
        return -1.0, None


def read_wallet_balance(wallet: str, network: str = "mainnet") -> float:
    """Read SOL balance (legacy CLI method)."""
    url = NETWORK_URLS.get(network, NETWORK_URLS["mainnet"])
    out, rc = _run_cmd(["solana", "balance", wallet, "--url", url])
    if rc != 0:
        return -1.0
    try:
        return float(out.split()[0])
    except (ValueError, IndexError):
        return -1.0


def read_spl_token_balances(wallet: str, network: str = "mainnet") -> list[TokenBalance]:
    """Read SPL token balances via JSON-RPC with failover."""
    data, err = rpc_call_safe(
        "getTokenAccountsByOwner",
        [wallet, {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
         {"encoding": "jsonParsed"}],
        network,
    )
    if err:
        return []

    known = KNOWN_TOKENS_MAINNET if network == "mainnet" else KNOWN_TOKENS_DEVNET
    tokens = []
    try:
        accounts = data["result"]["value"]
        for acct in accounts:
            info = acct["account"]["data"]["parsed"]["info"]
            mint = info["mint"]
            amount = float(info["tokenAmount"]["uiAmountString"])
            symbol = known.get(mint, mint[:8] + "...")
            tokens.append(TokenBalance(mint=mint, symbol=symbol, balance=amount))
    except (KeyError, TypeError, ValueError):
        pass
    return tokens


# ── Transaction history ─────────────────────────────────────────────────────

def get_signatures(wallet: str, network: str = "mainnet",
                   limit: int = 10) -> list[dict]:
    """Get recent transaction signatures for a wallet."""
    data, err = rpc_call_safe(
        "getSignaturesForAddress",
        [wallet, {"limit": limit}],
        network,
    )
    if err:
        return []
    try:
        return data["result"]
    except (KeyError, TypeError):
        return []


def get_transaction(signature: str, network: str = "mainnet") -> Optional[dict]:
    """Get parsed transaction details by signature."""
    data, err = rpc_call_safe(
        "getTransaction",
        [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}],
        network,
    )
    if err:
        return None
    try:
        return data["result"]
    except (KeyError, TypeError):
        return None


def get_transaction_history(wallet: Optional[str] = None,
                            network: str = "mainnet",
                            limit: int = 10) -> list[TransactionInfo]:
    """
    Get recent transaction history with parsed details.
    Returns list of TransactionInfo for the most recent `limit` transactions.
    """
    wallet = wallet or DEFAULT_WALLET
    sigs = get_signatures(wallet, network, limit)
    txs = []

    for sig_info in sigs:
        sig = sig_info.get("signature", "")
        slot = sig_info.get("slot", 0)
        block_time = sig_info.get("blockTime")
        err = sig_info.get("err")
        memo = sig_info.get("memo")

        # Get fee from full tx if available
        fee = 0
        tx_detail = get_transaction(sig, network)
        if tx_detail and tx_detail.get("meta"):
            fee = tx_detail["meta"].get("fee", 0)

        txs.append(TransactionInfo(
            signature=sig,
            slot=slot,
            block_time=block_time,
            success=err is None,
            fee=fee,
            memo=memo,
        ))

    return txs


# ── Jupiter swap stub ──────────────────────────────────────────────────────

def jupiter_quote(input_token: str, output_token: str,
                  amount: float) -> JupiterQuote:
    """
    Get a swap quote from Jupiter (simulated stub).
    In production, this would call https://quote-api.jup.ag/v6/quote.
    Currently returns a simulated quote for grant demonstration purposes.
    """
    input_mint = JUPITER_MINTS.get(input_token.upper(), input_token)
    output_mint = JUPITER_MINTS.get(output_token.upper(), output_token)

    # Simulated price ratios
    prices = {"SOL": 150.0, "USDC": 1.0, "USDT": 1.0}
    input_price = prices.get(input_token.upper(), 1.0)
    output_price = prices.get(output_token.upper(), 1.0)
    output_amount = (amount * input_price) / output_price

    return JupiterQuote(
        input_mint=input_mint,
        output_mint=output_mint,
        input_amount=amount,
        output_amount=round(output_amount, 6),
        price_impact_pct=0.05,
        route_plan=f"{input_token} -> {output_token} via Raydium",
        timestamp=time.time(),
    )


def jupiter_swap(input_token: str, output_token: str, amount: float,
                 wallet: Optional[str] = None) -> JupiterSwapResult:
    """
    Execute a Jupiter swap (simulated stub).
    In production, this would submit a signed transaction via Jupiter API.
    Returns simulated result for grant demonstration.
    """
    wallet = wallet or DEFAULT_WALLET
    quote = jupiter_quote(input_token, output_token, amount)

    # Simulate execution
    return JupiterSwapResult(
        success=True,
        input_mint=quote.input_mint,
        output_mint=quote.output_mint,
        input_amount=quote.input_amount,
        output_amount=quote.output_amount,
        tx_signature=f"simulated_{int(time.time())}_{input_token}_{output_token}",
        error=None,
    )


# ── Main wallet status ─────────────────────────────────────────────────────

def agent_wallet_status(
    wallet: Optional[str] = None,
    network: str = "mainnet",
    use_rpc: bool = True,
) -> WalletStatus:
    """
    Get unified wallet status combining SOL balance and SPL token balances.

    Args:
        wallet: Solana public key. Defaults to the agent's primary wallet.
        network: "mainnet", "devnet", or "testnet".
        use_rpc: If True, use JSON-RPC with failover. Else use CLI.

    Returns:
        WalletStatus with all balance information.
    """
    wallet = wallet or DEFAULT_WALLET
    if network not in RPC_ENDPOINTS:
        return WalletStatus(
            wallet=wallet,
            network=network,
            sol_balance=-1,
            is_active=False,
            error=f"Unknown network: {network}. Use: {list(RPC_ENDPOINTS.keys())}",
        )

    if use_rpc:
        sol, endpoint = read_wallet_balance_rpc(wallet, network)
    else:
        sol = read_wallet_balance(wallet, network)
        endpoint = NETWORK_URLS.get(network)

    tokens = read_spl_token_balances(wallet, network)
    error = None
    is_active = True

    if sol < 0:
        error = "Failed to read SOL balance - check network connectivity or wallet address"
        is_active = False

    return WalletStatus(
        wallet=wallet,
        network=network,
        sol_balance=sol,
        tokens=tokens,
        is_active=is_active,
        error=error,
        rpc_endpoint_used=endpoint,
    )


def read_crypto_identity() -> dict:
    """Return the agent's crypto identity configuration."""
    return {
        "wallet": DEFAULT_WALLET,
        "networks": list(RPC_ENDPOINTS.keys()),
        "supported_tokens": ["SOL", "USDC", "USDT", "PYUSD"],
        "rpc_endpoints": {k: v[0] for k, v in RPC_ENDPOINTS.items()},
        "capabilities": [
            "balance_check",
            "spl_token_balances",
            "transaction_history",
            "jupiter_swap_stub",
            "rpc_failover",
        ],
    }


# ── CLI entry point ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    net = sys.argv[1] if len(sys.argv) > 1 else "mainnet"
    status = agent_wallet_status(network=net)
    print(status.summary())
    print("---")
    print(status.to_json())

    print("\n--- Recent Transactions ---")
    txs = get_transaction_history(network=net, limit=5)
    for tx in txs:
        status_str = "OK" if tx.success else "FAIL"
        print(f"  [{status_str}] {tx.signature[:20]}... slot={tx.slot} fee={tx.fee}")

    print("\n--- Jupiter Quote (SOL->USDC) ---")
    q = jupiter_quote("SOL", "USDC", 1.0)
    print(json.dumps(q.to_dict(), indent=2))
