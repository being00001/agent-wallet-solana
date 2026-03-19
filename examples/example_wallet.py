"""
Example: Wallet Management
===========================

Demonstrates how to use the agent_wallet module for autonomous Solana agents.

Usage:
    python example_wallet.py --wallet <PUBKEY> --network mainnet

Features:
    - Check SOL and SPL token balances
    - View transaction history
    - Load keypair for signing transactions
"""

import argparse
import json
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_wallet import (
    AgentWallet,
    get_wallet_status,
    get_sol_balance,
    get_spl_token_balances,
    get_transaction_history,
    create_keypair,
    DEFAULT_WALLET,
    RPC_ENDPOINTS,
)


def example_basic_status():
    """Example 1: Basic wallet status check."""
    print("=" * 60)
    print("Example 1: Basic Wallet Status Check")
    print("=" * 60)
    
    # Using the function-based API
    status = get_wallet_status(DEFAULT_WALLET, network="mainnet")
    
    print(f"\nWallet: {status.wallet}")
    print(f"Network: {status.network}")
    print(f"SOL Balance: {status.sol_balance}")
    print(f"Active: {status.is_active}")
    
    if status.tokens:
        print("\nToken Balances:")
        for token in status.tokens:
            print(f"  - {token.symbol}: {token.balance}")
    
    if status.error:
        print(f"\nError: {status.error}")
    
    return status


def example_agent_wallet_class():
    """Example 2: Using AgentWallet class."""
    print("\n" + "=" * 60)
    print("Example 2: Using AgentWallet Class")
    print("=" * 60)
    
    # Create wallet instance
    wallet = AgentWallet(
        network="mainnet",
        wallet_address=DEFAULT_WALLET,
    )
    
    # Get status
    status = wallet.get_status()
    print(f"\nWallet Address: {wallet.wallet_address}")
    print(f"Can Sign: {wallet.has_signing_capability}")
    print(f"SOL Balance: {status.sol_balance}")
    
    # Get token balances
    tokens = wallet.get_token_balances()
    if tokens:
        print("\nToken Balances:")
        for token in tokens:
            print(f"  - {token.symbol}: {token.balance}")
    
    return wallet


def example_transaction_history():
    """Example 3: Get transaction history."""
    print("\n" + "=" * 60)
    print("Example 3: Transaction History")
    print("=" * 60)
    
    # Get recent transactions
    txs = get_transaction_history(DEFAULT_WALLET, network="mainnet", limit=5)
    
    if not txs:
        print("No transactions found")
        return
    
    print(f"\nRecent {len(txs)} transactions:")
    for tx in txs:
        status_str = "✓" if tx.success else "✗"
        print(f"  [{status_str}] {tx.signature[:32]}...")
        print(f"       Slot: {tx.slot}, Fee: {tx.fee} lamports")
        if tx.memo:
            print(f"       Memo: {tx.memo}")
    
    return txs


def example_keypair_operations():
    """Example 4: Keypair operations."""
    print("\n" + "=" * 60)
    print("Example 4: Keypair Operations")
    print("=" * 60)
    
    # Note: This would create a real keypair - commented out for safety
    # new_wallet_path = "/tmp/test_wallet.json"
    # address = create_keypair(new_wallet_path)
    # print(f"Created new wallet: {address}")
    
    # Check if default keypair exists
    default_path = os.path.expanduser("~/.config/solana/id.json")
    if os.path.exists(default_path):
        print(f"\nDefault keypair found at: {default_path}")
        print("You can use this for signing transactions")
    else:
        print(f"\nNo default keypair at: {default_path}")
        print("Create one with: solana-keygen new")


def example_network_switching():
    """Example 5: Switching between networks."""
    print("\n" + "=" * 60)
    print("Example 5: Network Switching")
    print("=" * 60)
    
    # Check available networks
    print("\nAvailable networks:")
    for network, endpoints in RPC_ENDPOINTS.items():
        print(f"  - {network}: {endpoints[0]}")
    
    # Example: Check status on different networks
    for network in ["mainnet", "devnet", "testnet"]:
        try:
            status = get_wallet_status(DEFAULT_WALLET, network=network, use_rpc=True)
            print(f"\n{network}: SOL={status.sol_balance}, Active={status.is_active}")
        except Exception as e:
            print(f"\n{network}: Error - {e}")


def main():
    """Main entry point for example script."""
    parser = argparse.ArgumentParser(description="Wallet Management Examples")
    parser.add_argument(
        "--wallet", "-w",
        default=DEFAULT_WALLET,
        help="Wallet public key"
    )
    parser.add_argument(
        "--network", "-n",
        default="mainnet",
        choices=["mainnet", "devnet", "testnet"],
        help="Solana network"
    )
    parser.add_argument(
        "--example", "-e",
        type=int,
        help="Run specific example (1-5)"
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON"
    )
    
    args = parser.parse_args()
    
    # Override default wallet
    global DEFAULT_WALLET
    DEFAULT_WALLET = args.wallet
    
    # Run examples
    if args.example:
        if args.example == 1:
            result = example_basic_status()
        elif args.example == 2:
            result = example_agent_wallet_class()
        elif args.example == 3:
            result = example_transaction_history()
        elif args.example == 4:
            result = example_keypair_operations()
        elif args.example == 5:
            result = example_network_switching()
        else:
            print(f"Unknown example: {args.example}")
            sys.exit(1)
        
        if args.json and hasattr(result, 'to_dict'):
            print("\n" + json.dumps(result.to_dict(), indent=2))
    else:
        # Run all examples
        example_basic_status()
        example_agent_wallet_class()
        example_transaction_history()
        example_keypair_operations()
        example_network_switching()
        
        print("\n" + "=" * 60)
        print("All examples completed!")
        print("=" * 60)


if __name__ == "__main__":
    main()
