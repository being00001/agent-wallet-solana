"""
Basic Usage Examples for Agent Wallet Tool
============================================

This file demonstrates how to use each of the three modules independently:
- agent_wallet.py: Wallet management operations
- dao_integration.py: DAO governance operations
- usdg_auto_claim.py: USDG auto-sweep operations

Run with: python examples/basic_usage.py
"""

import asyncio
import json
from solders.pubkey import Pubkey  # type: ignore[import-untyped]


# =============================================================================
# PART 1: Agent Wallet Module
# =============================================================================
def demo_agent_wallet():
    """Demonstrate wallet management operations."""
    print("\n" + "=" * 60)
    print("PART 1: Agent Wallet Module (agent_wallet.py)")
    print("=" * 60)
    
    # Import the module
    from agent_wallet import (
        agent_wallet_status,
        get_transaction_history,
        jupiter_quote,
        jupiter_swap,
        read_crypto_identity,
    )
    
    # Get wallet status (SOL + SPL tokens)
    print("\n--- Wallet Status ---")
    status = agent_wallet_status(network="mainnet")
    print(status.summary())
    
    # Get crypto identity
    print("\n--- Crypto Identity ---")
    identity = read_crypto_identity()
    print(f"Wallet: {identity['wallet']}")
    print(f"Networks: {identity['networks']}")
    print(f"Capabilities: {identity['capabilities']}")
    
    # Get transaction history
    print("\n--- Transaction History ---")
    txs = get_transaction_history(limit=5)
    print(f"Found {len(txs)} recent transactions:")
    for tx in txs:
        status_str = "OK" if tx.success else "FAIL"
        print(f"  [{status_str}] {tx.signature[:32]}...")
    
    # Jupiter swap quote
    print("\n--- Jupiter Swap Quote (SOL -> USDC) ---")
    quote = jupiter_quote("SOL", "USDC", 1.0)
    print(f"Input: {quote.input_amount} SOL")
    print(f"Output: {quote.output_amount} USDC")
    print(f"Route: {quote.route_plan}")
    
    # Jupiter swap execution (simulated)
    print("\n--- Jupiter Swap Execution (Simulated) ---")
    result = jupiter_swap("SOL", "USDC", 0.5)
    print(f"Success: {result.success}")
    print(f"Input: {result.input_amount} SOL")
    print(f"Output: {result.output_amount} USDC")
    print(f"Signature: {result.tx_signature}")


# =============================================================================
# PART 2: DAO Integration Module
# =============================================================================
def demo_dao_integration():
    """Demonstrate DAO governance operations."""
    print("\n" + "=" * 60)
    print("PART 2: DAO Integration Module (dao_integration.py)")
    print("=" * 60)
    
    # Import the module
    from dao_integration import (
        get_dao_info,
        list_daos,
        create_proposal,
        cast_vote,
        get_voting_power,
        get_proposal_status,
        get_active_proposals,
        VoteChoice,
        ProposalStatus,
    )
    
    # List popular DAOs
    print("\n--- List Popular DAOs ---")
    daos = list_daos("mainnet")
    print(f"Found {len(daos)} DAOs:")
    for dao in daos:
        print(f"  - {dao.name}: {dao.address[:20]}...")
    
    # Get DAO info
    print("\n--- DAO Info ---")
    if daos:
        dao = daos[0]
        print(f"Name: {dao.name}")
        print(f"Address: {dao.address}")
        print(f"Governance Program: {dao.governance_program_id[:20]}...")
        print(f"Token Mint: {dao.token_mint}")
    
    # Check voting power
    print("\n--- Voting Power ---")
    wallet = "3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb"
    if daos:
        power = get_voting_power(daos[0].address, wallet)
        print(f"Wallet: {wallet[:20]}...")
        print(f"Voting Power: {power.power}")
    
    # Create a proposal
    print("\n--- Create Proposal ---")
    if daos:
        proposal = create_proposal(
            dao=daos[0],
            title="Deploy Capital to DeFi Strategy",
            description="Proposal to allocate treasury funds to generate yield through validated DeFi protocols",
            proposer_wallet=wallet,
            vote_period_hours=72,
        )
        print(f"Title: {proposal.title}")
        print(f"Status: {proposal.status.value}")
        print(f"Pubkey: {proposal.pubkey[:40]}...")
        print(f"Vote End: {proposal.vote_end}")
    
    # Cast a vote
    print("\n--- Cast Vote ---")
    if daos:
        vote = cast_vote(
            proposal_pubkey=proposal.pubkey,
            voter_wallet=wallet,
            choice=VoteChoice.FOR,
            weight=100.0,
        )
        print(f"Choice: {vote.choice.value}")
        print(f"Weight: {vote.weight}")
    
    # Get proposal status
    print("\n--- Proposal Status ---")
    if daos:
        status = get_proposal_status(proposal.pubkey)
        print(f"Status: {status.status.value}")
        print(f"Votes For: {status.votes_for}")
        print(f"Votes Against: {status.votes_against}")
        print(f"Quorum Reached: {status.quorum_reached}")
    
    # Get active proposals
    print("\n--- Active Proposals ---")
    if daos:
        active = get_active_proposals(daos[0].address)
        print(f"Found {len(active)} active proposals:")
        for p in active:
            print(f"  - {p.title} ({p.status.value})")


# =============================================================================
# PART 3: USDG Auto-Claim Module
# =============================================================================
async def demo_usdg_auto_claim():
    """Demonstrate USDG auto-sweep operations."""
    print("\n" + "=" * 60)
    print("PART 3: USDG Auto-Claim Module (usdg_auto_claim.py)")
    print("=" * 60)
    
    # Import the module
    from usdg_auto_claim import (
        check_claimable,
        ClaimConfig,
        ClaimableBalance,
        SweepResult,
    )
    
    # Create configuration
    print("\n--- Configuration ---")
    config = ClaimConfig(
        network="mainnet",
        threshold_lamports=1_000_000,  # 1 USDG
        poll_interval_seconds=30,
        simulate_before_send=True,
    )
    print(f"Network: {config.network}")
    print(f"RPC: {config.rpc}")
    print(f"Threshold: {config.threshold_lamports} lamports")
    
    # Check claimable balance
    print("\n--- Check Claimable Balance ---")
    wallet = Pubkey.from_string("3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb")
    claim = await check_claimable(wallet, config)
    print(f"Wallet: {claim.wallet[:20]}...")
    print(f"Token: {claim.token_symbol}")
    print(f"Balance: {claim.balance_human}")
    print(f"Exceeds Threshold: {claim.exceeds_threshold}")
    print(f"Can Sweep: {claim.can_sweep}")
    print(f"SOL Balance: {claim.sol_balance_raw / 1e9} SOL")
    
    # Note: We don't actually execute a sweep in demo mode
    # as it requires a keypair and treasury address
    print("\n--- Sweep Would Be Executed If ---")
    print(f"  - Balance exceeds threshold: {claim.exceeds_threshold}")
    print(f"  - Has enough SOL for fees: {claim.can_sweep}")
    
    print("\n--- SweepResult Structure (Not Executed in Demo) ---")
    demo_result = SweepResult(
        success=True,
        signature="DemoSignature123...",
        amount_swept=1_000_000,
        fee_paid=5_000,
    )
    print(f"success: {demo_result.success}")
    print(f"signature: {demo_result.signature}")
    print(f"amount_swept: {demo_result.amount_swept}")
    print(f"fee_paid: {demo_result.fee_paid}")


# =============================================================================
# Main Entry Point
# =============================================================================
def main():
    """Run all demo functions."""
    print("=" * 60)
    print("Agent Wallet Tool - Basic Usage Examples")
    print("=" * 60)
    
    # Part 1: Agent Wallet (synchronous)
    demo_agent_wallet()
    
    # Part 2: DAO Integration (synchronous)
    demo_dao_integration()
    
    # Part 3: USDG Auto-Claim (asynchronous)
    asyncio.run(demo_usdg_auto_claim())
    
    print("\n" + "=" * 60)
    print("All demos completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
