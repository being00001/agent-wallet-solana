# Agent Wallet Tool for Solana

A comprehensive SDK for autonomous AI agents operating on the Solana blockchain. Built as part of the Solana Foundation grant proof-of-concept.

## Modules

This SDK consists of three integrated modules:

| Module | File | Description |
|--------|------|-------------|
| **Wallet Management** | `agent_wallet.py` | SOL/SPL balances, transaction history, Jupiter swaps |
| **DAO Integration** | `dao_integration.py` | Proposal creation, voting, status tracking |
| **USDG Auto-Claim** | `usdg_auto_claim.py` | Auto-sweep with error handling and gas optimization |

## Features

### agent_wallet.py - Wallet Management
| Feature | Description |
|---------|-------------|
| **SOL Balance** | Read SOL balance via JSON-RPC or CLI fallback |
| **SPL Tokens** | Enumerate SPL token accounts (USDC, USDT, PYUSD, etc.) |
| **Transaction History** | `getSignaturesForAddress` + `getTransaction` for recent txs |
| **Jupiter Swap Stub** | Simulated quote/execute for SOL/USDC/USDT swaps |
| **RPC Failover** | Automatic retry across 3 endpoints (mainnet-beta, extrnode, ankr) |
| **Multi-Network** | Mainnet, devnet, testnet support |

### dao_integration.py - DAO Governance
| Feature | Description |
|---------|-------------|
| **DAO Discovery** | Query and list popular DAOs (Realms, Squads) |
| **Proposal Creation** | Create proposals for agent collectives |
| **Voting** | Cast votes, check voting power |
| **Status Tracking** | Monitor proposal states |
| **Event Listening** | Real-time proposal updates |
| **Error Handling** | Robust error handling for all operations |

### usdg_auto_claim.py - USDG Auto-Sweep
| Feature | Description |
|---------|-------------|
| **Balance Monitoring** | Check USDG/USDC balances above threshold |
| **Auto-Sweep** | Automatically transfer to treasury when threshold exceeded |
| **Retry Mechanism** | Exponential backoff with jitter |
| **Circuit Breaker** | Prevent cascading failures |
| **Gas Optimization** | Dynamic priority fees, compute unit optimization |
| **Transaction Simulation** | Verify before execution |

## Quick Start

### Installation

```bash
cd agent_wallet_tool
pip install -r requirements.txt
```

### Wallet Management

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

### DAO Integration

```python
from dao_integration import (
    get_dao_info, list_daos, create_proposal,
    cast_vote, get_voting_power, get_proposal_status,
    get_active_proposals, VoteChoice
)

# List popular DAOs
daos = list_daos("mainnet")
print(f"Found {len(daos)} DAOs")

# Get DAO info
dao = get_dao_info("GqTswD7sV2xJ5xR4Qf5hZ6k8Lm9pN0wX2Y3zA4B5cD6E7f8G")

# Check voting power
power = get_voting_power(dao.address, "AgentWallet...")
print(f"Voting power: {power.power}")

# Create a proposal
proposal = create_proposal(
    dao=dao,
    title="Agent Collective Decision",
    description="Deploy capital to DeFi strategy",
    proposer_wallet="AgentWallet...",
)

# Cast a vote
vote = cast_vote(
    proposal_pubkey=proposal.pubkey,
    voter_wallet="AgentWallet...",
    choice=VoteChoice.FOR,
    weight=100,
)

# Track proposal status
status = get_proposal_status(proposal.pubkey)
print(f"Proposal status: {status.status}")
```

### USDG Auto-Claim

```python
import asyncio
from solders.pubkey import Pubkey
from usdg_auto_claim import check_claimable, execute_sweep, ClaimConfig

async def main():
    config = ClaimConfig(network="mainnet", threshold_lamports=1_000_000)
    wallet = Pubkey.from_string("YourWalletAddress...")
    
    # Check claimable balance
    claim = await check_claimable(wallet, config)
    print(f"Balance: {claim.balance_human} USDG")
    print(f"Exceeds threshold: {claim.exceeds_threshold}")
    
    # Execute sweep if needed
    if claim.can_sweep:
        result = await execute_sweep(wallet_keypair, treasury, config)
        print(f"Sweep result: {result.success}")

asyncio.run(main())
```

## CLI Usage

### Wallet Management
```bash
python agent_wallet.py              # mainnet (default)
python agent_wallet.py devnet       # devnet
python agent_wallet.py testnet      # testnet
```

### DAO Integration
```bash
python dao_integration.py              # List DAOs on mainnet
python dao_integration.py devnet       # List DAOs on devnet
python dao_integration.py --dao <addr> # Get specific DAO info
```

### USDG Auto-Claim
```bash
# Check balance
python usdg_auto_claim.py --check --wallet <PUBKEY> --network mainnet

# Single sweep
python usdg_auto_claim.py --sweep --wallet <PUBKEY> --treasury <PUBKEY> --keypair <PATH>

# Continuous monitoring
python usdg_auto_claim.py --monitor --wallet <PUBKEY> --treasury <PUBKEY> --keypair <PATH>
```

## RPC Failover

The tool automatically retries failed RPC calls across multiple endpoints:

```
Attempt 1: api.mainnet-beta.solana.com
Attempt 2: solana-mainnet.rpc.extrnode.com
Attempt 3: rpc.ankr.com/solana
```

Each call retries up to 3 times with endpoint rotation. Network errors, timeouts, and RPC errors all trigger failover.

## Examples

See the `examples/` directory for comprehensive usage examples:

- `basic_usage.py` - How to use each module independently
- `integrated_agent.py` - How an autonomous agent uses all three modules together

## Testing

```bash
cd agent_wallet_tool
pytest test_agent_wallet.py -v
pytest test_dao_integration.py -v
```

## Grant Relevance

This SDK demonstrates key capabilities for the Solana Foundation grant:

1. **Autonomous agent wallet management** — AI agents can monitor balances and transactions without human intervention
2. **DeFi integration readiness** — Jupiter swap stub shows the integration pattern for production DEX swaps
3. **DAO governance participation** — Autonomous agents can create proposals and vote on behalf of collectives
4. **Automated treasury operations** — USDG auto-sweep ensures efficient capital movement
5. **Production resilience** — RPC failover, circuit breakers, and retry mechanisms ensure agents remain operational

## Architecture

```
agent_wallet_tool/
├── agent_wallet.py          # Wallet management module
├── dao_integration.py       # DAO governance module
├── usdg_auto_claim.py      # USDG auto-sweep module
├── test_agent_wallet.py    # Wallet tests
├── test_dao_integration.py # DAO tests
├── examples/               # Usage examples
│   ├── basic_usage.py
│   └── integrated_agent.py
├── requirements.txt        # Dependencies
└── README.md               # This file
```

## Configuration

| Constant | Description | Default |
|----------|-------------|---------|
| `DEFAULT_WALLET` | Agent's primary wallet pubkey | `3WJxpvb...` |
| `MAX_RPC_RETRIES` | Max failover attempts | 3 |
| `RPC_TIMEOUT` | Per-request timeout (seconds) | 15 |
| `USDG_MINT_MAINNET` | USDG token mint address | `2u1tszS...` |

## License

Part of the Being autonomous agent framework.
