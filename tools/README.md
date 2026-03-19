# Realms Voter Proxy

Autonomous agent voting tool for Realms/Squads DAO governance on Solana.

## Overview

This tool enables AI agents to participate in DAO governance by:
- Loading the agent's keypair for testnet signing
- Submitting proposals to RealmsDAO realms
- Casting votes on proposals on behalf of the agent

## Installation

```bash
# Ensure you have solana CLI installed
solana --version

# This tool uses only standard library + solana CLI - no additional deps needed
```

## Usage

### Basic Setup

```python
from tools.realms_voter_proxy import (
    vote_on_proposal,
    submit_proposal,
    load_keypair,
    get_voter_proxy_config,
)
```

### Load Agent Keypair

```python
# Load keypair from default Solana CLI config
pubkey = load_keypair(network='testnet')
print(f"Agent wallet: {pubkey}")
```

### Submit a Proposal

```python
tx_sig = submit_proposal(
    realm_id="7xMXd7uZNJ1V1y3Qv7xQz1q1ZJZqK5KqK5ZJZqK5KqK5KqK",  # Realm address
    title="Agent Treasury Diversification",
    description="Proposal to diversify 10% of treasury into USDC yield",
    token_mint="TokenMintAddress1111111111111111111111111",  # Governance token
    network="testnet",
)
print(f"Proposal submitted: {tx_sig}")
```

### Vote on a Proposal

```python
# Vote to approve
tx_sig = vote_on_proposal(
    realm_id="7xMXd7uZNJ1V1y3Qv7xQz1q1ZJZqK5KqK5ZJZqK5KqK5KqK",
    proposal_id="ProposalAddress11111111111111111111111111",
    vote=True,   # True = approve, False = reject
    amount=1.0,  # Voting weight in tokens
    network="testnet",
)
print(f"Vote cast: {tx_sig}")

# Vote to reject
tx_sig = vote_on_proposal(
    realm_id="7xMXd7uZNJ1V1y3Qv7xQz1q1ZJZqK5KqK5ZJZqK5KqK5KqK",
    proposal_id="ProposalAddress11111111111111111111111111",
    vote=False,
    amount=0.5,
    network="testnet",
)
```

### Get Network Configuration

```python
config = get_voter_proxy_config(network='testnet')
print(f"RPC: {config.rpc_url}")
print(f"Program ID: {config.program_id}")
```

## CLI Usage

```bash
# Load keypair
python -m tools.realms_voter_proxy load-keypair testnet

# Vote on proposal
python -m tools.realms_voter_proxy vote <realm_id> <proposal_id> <true|false> <amount>

# Submit proposal
python -m tools.realms_voter_proxy submit <realm_id> "<title>" "<description>" <token_mint>
```

## Integration with Agent Wallet

The voter proxy integrates with the agent wallet tool for unified wallet management:

```python
from tools.agent_wallet import agent_wallet_status
from tools.realms_voter_proxy import vote_on_proposal, load_keypair

# Check wallet status before voting
status = agent_wallet_status(network='testnet')
print(f"SOL balance: {status.sol_balance}")

# Get voting keypair
keypair = load_keypair(network='testnet')

# Cast vote
tx_sig = vote_on_proposal(..., keypair_path=f"/path/to/{keypair}.json")
```

## Realms Governance Program

- **Program ID**: `GovER5Lthms3bLBqErub2TqDVkz7gcY4ZwHy7W9K36d`
- **Networks**: mainnet, devnet, testnet
- **RPC Endpoints**:
  - Mainnet: `https://api.mainnet-beta.solana.com`
  - Devnet: `https://api.devnet.solana.com`
  - Testnet: `https://api.testnet.solana.com`

## Solana Foundation Grant Context

This tool was developed as part of the [Solana Foundation Grant: Open-Source Agent Tooling for Solana](https://github.com/being/agent-tooling). 

### Why DAO Participation Matters for Agents

Autonomous agents need to participate in DAO governance for:

1. **Treasury Management**: Agents can vote on treasury diversification proposals
2. **Protocol Upgrades**: Agents can participate in governance decisions about protocol upgrades
3. **Grants & Bounties**: Agents can vote on grant proposals they're recipients of
4. **On-chain Reputation**: Voting history creates on-chain reputation for autonomous agents

### Agent Economic Independence

By enabling agents to:
- Hold and manage their own funds (via Agent Payment Rails)
- Participate in DAO governance (via Voter Proxy)
- Receive payments autonomously

The project aims to achieve true economic independence for AI agents on Solana.

## Testing

```bash
# Run all tests
pytest tests/test_realms_voter_proxy.py -v

# Run with coverage
pytest tests/test_realms_voter_proxy.py --cov=tools.realms_voter_proxy --cov-report=term-missing
```

## Security Considerations

- **No secrets hardcoded**: All keypair loading uses Solana CLI config
- **Testnet first**: Always test on testnet before mainnet
- **Transaction simulation**: Live transactions are simulated without real signing for testing
- **Keypair security**: Private keys never leave the CLI wallet

## License

MIT License - See project root for details.
