# Agent Wallet Tool for Solana

A comprehensive wallet management tool for autonomous AI agents operating on the Solana blockchain. Built as part of the Solana Foundation grant proof-of-concept.

## Features

| Feature | Description |
|---------|-------------|
| **SOL Balance** | Read SOL balance via JSON-RPC or CLI fallback |
| **SPL Tokens** | Enumerate SPL token accounts (USDC, USDT, PYUSD, etc.) |
| **Transaction History** | `getSignaturesForAddress` + `getTransaction` for recent 10 txs |
| **Jupiter Swap Stub** | Simulated quote/execute for SOL/USDC/USDT swaps |
| **RPC Failover** | Automatic retry across 3 endpoints (mainnet-beta, extrnode, ankr) |
| **Multi-Network** | Mainnet, devnet, testnet support |

## Quick Start

```python
from agent_wallet import agent_wallet_status, get_transaction_history
from agent_wallet import jupiter_quote, jupiter_swap

# Get full wallet status (SOL + SPL tokens)
status = agent_wallet_status()
print(status.summary())

# Get recent transaction history
txs = get_transaction_history(limit=10)
for tx in txs:
    print(f"[{'OK' if tx.success else 'FAIL'}] {tx.signature[:20]}... fee={tx.fee}")

# Jupiter swap quote (simulated)
quote = jupiter_quote("SOL", "USDC", 1.0)
print(f"1 SOL = {quote.output_amount} USDC")

# Execute swap (simulated stub)
result = jupiter_swap("SOL", "USDC", 1.0)
print(f"Swap tx: {result.tx_signature}")
```

## CLI Usage

```bash
python agent_wallet.py              # mainnet (default)
python agent_wallet.py devnet       # devnet
python agent_wallet.py testnet      # testnet
```

## RPC Failover

The tool automatically retries failed RPC calls across multiple endpoints:

```
Attempt 1: api.mainnet-beta.solana.com
Attempt 2: solana-mainnet.rpc.extrnode.com
Attempt 3: rpc.ankr.com/solana
```

Each call retries up to 3 times with endpoint rotation. Network errors, timeouts, and RPC errors all trigger failover.

## API Reference

### `agent_wallet_status(wallet=None, network="mainnet", use_rpc=True)`
Returns a `WalletStatus` with SOL balance, SPL tokens, and connection info.

### `get_transaction_history(wallet=None, network="mainnet", limit=10)`
Returns list of `TransactionInfo` for recent transactions.

### `jupiter_quote(input_token, output_token, amount)`
Returns a `JupiterQuote` with simulated swap pricing.

### `jupiter_swap(input_token, output_token, amount, wallet=None)`
Returns a `JupiterSwapResult` with simulated swap execution.

### `read_crypto_identity()`
Returns the agent's crypto identity configuration including capabilities.

### `rpc_call(method, params, network="mainnet")`
Low-level JSON-RPC call with automatic failover.

## Testing

```bash
cd agent_wallet_tool
pytest test_agent_wallet.py -v
```

25+ tests covering:
- Data class creation and serialization
- RPC failover (success, error rotation, all-fail)
- SOL balance via RPC and CLI
- SPL token balance parsing
- Transaction history retrieval
- Jupiter quote/swap simulation
- Network configuration validation
- CLI command edge cases (timeout, not found)
- Error handling for all code paths

## Grant Relevance

This tool demonstrates key capabilities for the Solana Foundation grant:

1. **Autonomous agent wallet management** — AI agents can monitor balances and transactions without human intervention
2. **DeFi integration readiness** — Jupiter swap stub shows the integration pattern for production DEX swaps
3. **Production resilience** — RPC failover ensures agents remain operational when individual endpoints fail
4. **Multi-token awareness** — SPL token parsing enables agents to manage diverse token portfolios
5. **Comprehensive testing** — 25+ tests ensure reliability for mission-critical financial operations

## Architecture

```
agent_wallet_tool/
├── agent_wallet.py          # Main module
├── test_agent_wallet.py     # Comprehensive pytest suite
└── README.md                # This file
```

## Configuration

| Constant | Description | Default |
|----------|-------------|---------|
| `DEFAULT_WALLET` | Agent's primary wallet pubkey | `3WJxpvb...` |
| `MAX_RPC_RETRIES` | Max failover attempts | 3 |
| `RPC_TIMEOUT` | Per-request timeout (seconds) | 15 |

## License

Part of the Being autonomous agent framework.
