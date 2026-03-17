"""
Agent Wallet Tool for Solana

Provides unified wallet status for autonomous agents operating on Solana.
Combines SOL balance, SPL token balances (USDC, USDG), and network health
into a single cohesive tool suitable for workspace integration.

Usage:
    from tools.agent_wallet import agent_wallet_status
    status = agent_wallet_status()  # defaults to mainnet
    status = agent_wallet_status(network="devnet")
    status = agent_wallet_status(wallet="<pubkey>", network="mainnet")
"""

import json
import subprocess
from dataclasses import dataclass, field, asdict
from typing import Optional

# Default agent wallet
DEFAULT_WALLET = "3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb"

# Well-known SPL token mints on mainnet
KNOWN_TOKENS_MAINNET = {
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
    "2b1kV6DkPAnxd5ixfnxCpjxmKwqjjaYmCZfHsFu24GXo": "PYUSD",
    # USDG mint - add when known
}

# Devnet tokens may differ
KNOWN_TOKENS_DEVNET = {
    "CXk2AMBfi3TwaEL2468s6zP8xq9NxTXjp9gjMgzeUynM": "UNKNOWN_SPL",
}

NETWORK_URLS = {
    "mainnet": "https://api.mainnet-beta.solana.com",
    "devnet": "https://api.devnet.solana.com",
    "testnet": "https://api.testnet.solana.com",
}


@dataclass
class TokenBalance:
    mint: str
    symbol: str
    balance: float


@dataclass
class WalletStatus:
    wallet: str
    network: str
    sol_balance: float
    tokens: list = field(default_factory=list)
    is_active: bool = True
    error: Optional[str] = None

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
        if self.error:
            lines.append(f"Error: {self.error}")
        return "\n".join(lines)


def _run_cmd(args: list[str], timeout: int = 30) -> tuple[str, int]:
    """Run a CLI command and return (stdout, returncode)."""
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "timeout", 1
    except FileNotFoundError:
        return "command_not_found", 1


def read_wallet_balance(wallet: str, network: str = "mainnet") -> float:
    """Read SOL balance for a wallet on the given network."""
    url = NETWORK_URLS.get(network, NETWORK_URLS["mainnet"])
    out, rc = _run_cmd(["solana", "balance", wallet, "--url", url])
    if rc != 0:
        return -1.0
    # Output format: "0.1197617 SOL"
    try:
        return float(out.split()[0])
    except (ValueError, IndexError):
        return -1.0


def read_spl_token_balances(wallet: str, network: str = "mainnet") -> list[TokenBalance]:
    """Read all SPL token balances for a wallet."""
    url = NETWORK_URLS.get(network, NETWORK_URLS["mainnet"])
    out, rc = _run_cmd(["spl-token", "accounts", "--owner", wallet, "--url", url])
    if rc != 0:
        return []

    known = KNOWN_TOKENS_MAINNET if network == "mainnet" else KNOWN_TOKENS_DEVNET
    tokens = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("Token") or line.startswith("---"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            mint = parts[0]
            try:
                balance = float(parts[1])
            except ValueError:
                continue
            symbol = known.get(mint, mint[:8] + "...")
            tokens.append(TokenBalance(mint=mint, symbol=symbol, balance=balance))
    return tokens


def agent_wallet_status(
    wallet: Optional[str] = None,
    network: str = "mainnet",
) -> WalletStatus:
    """
    Get unified wallet status combining SOL balance and SPL token balances.

    Args:
        wallet: Solana public key. Defaults to the agent's primary wallet.
        network: "mainnet", "devnet", or "testnet".

    Returns:
        WalletStatus with all balance information.
    """
    wallet = wallet or DEFAULT_WALLET
    if network not in NETWORK_URLS:
        return WalletStatus(
            wallet=wallet,
            network=network,
            sol_balance=-1,
            is_active=False,
            error=f"Unknown network: {network}. Use: {list(NETWORK_URLS.keys())}",
        )

    sol = read_wallet_balance(wallet, network)
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
    )


def read_crypto_identity() -> dict:
    """Return the agent's crypto identity configuration."""
    return {
        "wallet": DEFAULT_WALLET,
        "networks": list(NETWORK_URLS.keys()),
        "supported_tokens": ["SOL", "USDC", "USDG"],
        "rpc_endpoints": NETWORK_URLS,
    }


# CLI entry point for quick checks
if __name__ == "__main__":
    import sys

    net = sys.argv[1] if len(sys.argv) > 1 else "mainnet"
    status = agent_wallet_status(network=net)
    print(status.summary())
    print("---")
    print(status.to_json())
