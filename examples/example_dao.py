"""
Example: DAO Integration
=========================

Demonstrates how to use the dao_integration module for autonomous agent collectives.

Usage:
    python example_dao.py --realm <REALM_ID> --network mainnet

Features:
    - Create proposals for agent collective decisions
    - Query proposal status and results
    - Cast votes with voting power
    - Query voting power

Supported DAOs:
    - Realms (Solana DAO governance)
    - Squads (Multisig DAO)

Realms Governance Program: GovER5Lthms3bLBqErub2TqDVkz7gcY4ZwHy7W9K36d
Squads Program: SMPLecH83mYq4w8g6Y2Lc6m2ZBCuCoqE4vMJH3WMM2k
"""

import argparse
import json
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dao_integration import (
    DAOClient,
    create_proposal,
    get_proposals,
    get_proposal_results,
    cast_vote,
    get_voting_power,
    get_vote_records,
    REALMS_GOVERNANCE_PROGRAM_ID,
    SQUADS_PROGRAM_ID,
    NETWORK_URLS,
    PROPOSAL_STATUS_VOTING,
)


# Example addresses
EXAMPLE_REALM = "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"
EXAMPLE_TOKEN_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"  # USDC
EXAMPLE_VOTER = "3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb"


def example_get_config():
    """Example 1: Get DAO configuration."""
    print("=" * 60)
    print("Example 1: DAO Configuration")
    print("=" * 60)
    
    print("\nSupported Networks:")
    for network, url in NETWORK_URLS.items():
        print(f"  - {network}: {url}")
    
    print("\nProgram IDs:")
    print(f"  - Realms: {REALMS_GOVERNANCE_PROGRAM_ID}")
    print(f"  - Squads: {SQUADS_PROGRAM_ID}")
    
    print("\nProposal Statuses:")
    print(f"  - Draft: draft")
    print(f"  - Voting: {PROPOSAL_STATUS_VOTING}")
    print(f"  - Executed: executed")
    print(f"  - Cancelled: cancelled")


def example_dao_client():
    """Example 2: Create DAO client."""
    print("\n" + "=" * 60)
    print("Example 2: DAO Client")
    print("=" * 60)
    
    # Create DAO client for Realms
    dao = DAOClient(
        network="mainnet",
        dao_type="realms",
    )
    
    print(f"\nDAO Client created:")
    print(f"  Network: {dao.network}")
    print(f"  DAO Type: {dao.dao_type}")
    print(f"  RPC URL: {dao.config.rpc_url}")
    print(f"  Program ID: {dao.config.program_id}")
    
    # Create client for Squads
    squads_dao = DAOClient(
        network="mainnet",
        dao_type="squads",
    )
    
    print(f"\nSquads DAO Client:")
    print(f"  Program ID: {squads_dao.config.program_id}")
    
    return dao


def example_create_proposal():
    """Example 3: Create a proposal."""
    print("\n" + "=" * 60)
    print("Example 3: Create Proposal")
    print("=" * 60)
    
    # Note: This would create a real proposal on-chain
    # For demo, we show the function call structure
    
    print(f"\nRealm: {EXAMPLE_REALM}")
    print(f"Token Mint: {EXAMPLE_TOKEN_MINT}")
    
    # Example proposal data
    proposal_data = {
        "title": "Deploy Treasury Funds to Liquidity Pool",
        "description": "Proposal to deploy 1000 USDC to Raydium liquidity pool for yield generation",
        "token_mint": EXAMPLE_TOKEN_MINT,
    }
    
    print(f"\nProposal Details:")
    for key, value in proposal_data.items():
        print(f"  {key}: {value}")
    
    # In production, uncomment to execute:
    # tx_sig = create_proposal(
    #     realm_id=EXAMPLE_REALM,
    #     title=proposal_data["title"],
    #     description=proposal_data["description"],
    #     token_mint=proposal_data["token_mint"],
    #     network="mainnet",
    # )
    # print(f"\nTransaction: {tx_sig}")
    
    print("\nNote: Proposal creation disabled for demo")
    print("To enable, provide a valid keypair and sufficient governance tokens")


def example_get_proposals():
    """Example 4: Get proposals for a DAO."""
    print("\n" + "=" * 60)
    print("Example 4: Get Proposals")
    print("=" * 60)
    
    # Get proposals
    proposals = get_proposals(EXAMPLE_REALM, network="mainnet")
    
    print(f"\nFound {len(proposals)} proposals for realm {EXAMPLE_REALM[:20]}...")
    
    if not proposals:
        print("No proposals found (this is expected for mock data)")
        return proposals
    
    for prop in proposals:
        print(f"\n  Title: {prop['title']}")
        print(f"  Status: {prop['status']}")
        print(f"  ID: {prop['proposal_id'][:20]}...")
    
    return proposals


def example_get_voting_power():
    """Example 5: Get voting power."""
    print("\n" + "=" * 60)
    print("Example 5: Get Voting Power")
    print("=" * 60)
    
    voter = EXAMPLE_VOTER
    
    # Get voting power
    power = get_voting_power(voter, EXAMPLE_REALM, network="mainnet")
    
    print(f"\nVoter: {voter}")
    print(f"Realm: {EXAMPLE_REALM[:20]}...")
    print(f"Voting Power: {power}")
    
    if power > 0:
        print("✓ Voter has governance tokens")
    else:
        print("✗ No governance tokens found")
    
    return power


def example_cast_vote():
    """Example 6: Cast a vote."""
    print("\n" + "=" * 60)
    print("Example 6: Cast Vote")
    print("=" * 60)
    
    # Example proposal ID
    proposal_id = "example_proposal_123"
    vote_amount = 1.0
    
    print(f"\nProposal: {proposal_id[:20]}...")
    print(f"Vote: Approve")
    print(f"Amount: {vote_amount}")
    
    # In production, uncomment to execute:
    # tx_sig = cast_vote(
    #     proposal_id=proposal_id,
    #     vote=True,  # True = approve, False = reject
    #     amount=vote_amount,
    #     network="mainnet",
    # )
    # print(f"\nTransaction: {tx_sig}")
    
    print("\nNote: Vote casting disabled for demo")
    print("To enable, provide a valid keypair and voting power")


def example_get_results():
    """Example 7: Get proposal results."""
    print("\n" + "=" * 60)
    print("Example 7: Get Proposal Results")
    print("=" * 60)
    
    # Example proposal
    proposal_id = "example_proposal_123"
    
    # Get results
    results = get_proposal_results(proposal_id, network="mainnet")
    
    print(f"\nProposal: {proposal_id[:20]}...")
    print(f"Status: {results['status']}")
    
    print(f"\nVote Counts:")
    for option, count in results['votes'].items():
        pct = results['percentages'].get(option, 0)
        print(f"  - {option}: {count} ({pct}%)")
    
    print(f"\nTotal Votes: {results['total_votes']}")
    print(f"Quorum: {results['quorum']}")
    print(f"Quorum Reached: {results['quorum_reached']}")
    print(f"Winner: {results['winning_option']}")
    
    return results


def example_vote_records():
    """Example 8: Get vote records."""
    print("\n" + "=" * 60)
    print("Example 8: Get Vote Records")
    print("=" * 60)
    
    proposal_id = "example_proposal_123"
    
    # Get vote records
    records = get_vote_records(proposal_id, network="mainnet")
    
    print(f"\nProposal: {proposal_id[:20]}...")
    print(f"Found {len(records)} vote records")
    
    for record in records:
        print(f"\n  Voter: {record['voter'][:20]}...")
        print(f"  Vote: {record['vote']}")
        print(f"  Amount: {record['amount']}")
    
    return records


def example_agent_collective_workflow():
    """Example 9: Complete agent collective workflow."""
    print("\n" + "=" * 60)
    print("Example 9: Agent Collective Workflow")
    print("=" * 60)
    
    print("""
This example demonstrates a complete workflow for an agent collective:

1. Initialize DAO Client
   - Connect to Realms DAO
   - Load agent keypair

2. Check Voting Power
   - Query governance token balance
   - Determine voting weight

3. Review Active Proposals
   - Get list of proposals in voting state
   - Analyze proposal details

4. Cast Votes
   - Vote on proposals based on strategy
   - Submit transactions

5. Monitor Results
   - Check proposal outcomes
   - Track execution status

This enables autonomous agents to participate in DAO governance
without manual intervention.
""")


def main():
    """Main entry point for example script."""
    parser = argparse.ArgumentParser(description="DAO Integration Examples")
    parser.add_argument(
        "--realm",
        default=EXAMPLE_REALM,
        help="DAO/Realm ID"
    )
    parser.add_argument(
        "--network", "-n",
        default="mainnet",
        choices=["mainnet", "devnet", "testnet"],
        help="Solana network"
    )
    parser.add_argument(
        "--dao-type", "-d",
        default="realms",
        choices=["realms", "squads"],
        help="DAO type"
    )
    parser.add_argument(
        "--example", "-e",
        type=int,
        help="Run specific example (1-9)"
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON"
    )
    
    args = parser.parse_args()
    
    # Update global example realm
    global EXAMPLE_REALM
    EXAMPLE_REALM = args.realm
    
    # Run examples
    if args.example:
        if args.example == 1:
            result = example_get_config()
        elif args.example == 2:
            result = example_dao_client()
        elif args.example == 3:
            result = example_create_proposal()
        elif args.example == 4:
            result = example_get_proposals()
        elif args.example == 5:
            result = example_get_voting_power()
        elif args.example == 6:
            result = example_cast_vote()
        elif args.example == 7:
            result = example_get_results()
        elif args.example == 8:
            result = example_vote_records()
        elif args.example == 9:
            result = example_agent_collective_workflow()
        else:
            print(f"Unknown example: {args.example}")
            sys.exit(1)
        
        if args.json and isinstance(result, (list, dict)):
            print("\n" + json.dumps(result, indent=2))
    else:
        # Run all examples
        example_get_config()
        example_dao_client()
        example_create_proposal()
        example_get_proposals()
        example_get_voting_power()
        example_cast_vote()
        example_get_results()
        example_vote_records()
        example_agent_collective_workflow()
        
        print("\n" + "=" * 60)
        print("All examples completed!")
        print("=" * 60)


if __name__ == "__main__":
    main()
