"""
Example: USDG Auto-Claim
========================

Demonstrates how to use the usdg_auto_claim module for autonomous agents.

Usage:
    python example_usdg_claim.py --wallet <PUBKEY> --treasury <TREASURY> --network mainnet

Features:
    - Check USDG balance
    - Check claimable amount
    - Auto-sweep to treasury
    - Monitor for incoming USDG

USDG (Global Dollar) by Paxos is used for Superteam Earn grant payouts.
Mint Address: 2u1tszSeqZ3qBWF3uNGPFc8TzMk2tdiwknnRMWGWjGWH
"""

import argparse
import json
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from usdg_auto_claim import (
    USDGClaimer,
    USDGConfig,
    get_usdg_balance,
    check_claimable_amount,
    auto_sweep_to_treasury,
    USDG_MINT_MAINNET,
    RPC_ENDPOINTS,
)


# Default treasury address for demo
DEFAULT_TREASURY = "3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb"


def example_check_balance():
    """Example 1: Check USDG balance."""
    print("=" * 60)
    print("Example 1: Check USDG Balance")
    print("=" * 60)
    
    wallet = "3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb"  # Example wallet
    
    balance = get_usdg_balance(wallet, network="mainnet")
    
    print(f"\nWallet: {wallet}")
    print(f"USDG Balance: {balance}")
    print(f"USDG Mint: {USDG_MINT_MAINNET}")
    
    return balance


def example_config_and_claimer():
    """Example 2: Configure and create USDGClaimer."""
    print("\n" + "=" * 60)
    print("Example 2: Configure USDGClaimer")
    print("=" * 60)
    
    # Create configuration
    config = USDGConfig(
        network="mainnet",
        rpc_url="https://api.mainnet-beta.solana.com",
        keypair_path=os.path.expanduser("~/.config/solana/id.json"),
        treasury_address=DEFAULT_TREASURY,
        threshold=100.0,  # Auto-claim when balance > 100 USDG
        priority_fee=1000,  # Micro lamports
    )
    
    print(f"\nConfiguration:")
    print(f"  Network: {config.network}")
    print(f"  RPC URL: {config.rpc_url}")
    print(f"  Treasury: {config.treasury_address}")
    print(f"  Threshold: {config.threshold} USDG")
    print(f"  Priority Fee: {config.priority_fee} micro lamports")
    
    # Create claimer
    claimer = USDGClaimer(config)
    
    print(f"\nClaimer created successfully")
    print(f"  Has keypair: {claimer.keypair is not None}")
    
    return claimer


def example_check_claimable():
    """Example 3: Check claimable amount."""
    print("\n" + "=" * 60)
    print("Example 3: Check Claimable Amount")
    print("=" * 60)
    
    wallet = "3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb"
    
    # Check current balance
    balance = get_usdg_balance(wallet, network="mainnet")
    print(f"\nCurrent USDG balance: {balance}")
    
    # Check if above threshold
    threshold = 100.0
    claimable = check_claimable_amount(wallet, threshold, network="mainnet")
    
    print(f"Threshold: {threshold}")
    print(f"Claimable amount: {claimable}")
    
    if claimable > 0:
        print("✓ Balance exceeds threshold - eligible for auto-sweep")
    else:
        print("✗ Balance below threshold")
    
    return claimable


def example_auto_sweep():
    """Example 4: Auto-sweep to treasury."""
    print("\n" + "=" * 60)
    print("Example 4: Auto-Sweep to Treasury")
    print("=" * 60)
    
    # Note: This would execute a real transaction - for demo purposes only
    # In production, uncomment to execute:
    
    # config = USDGConfig(
    #     network="mainnet",
    #     treasury_address=DEFAULT_TREASURY,
    #     threshold=100.0,
    # )
    # claimer = USDGClaimer(config)
    # result = claimer.check_and_claim()
    # print(f"Sweep result: {result}")
    
    print("\nNote: Auto-sweep disabled for demo safety")
    print("To enable, uncomment the code above and provide a valid keypair")
    
    print(f"\nWould sweep from wallet to treasury: {DEFAULT_TREASURY}")
    print("This requires:")
    print("  1. A valid keypair file")
    print("  2. USDG balance above threshold (100.0)")
    print("  3. Enough SOL for transaction fees")


def example_monitor_mode():
    """Example 5: Monitor for incoming USDG."""
    print("\n" + "=" * 60)
    print("Example 5: Monitor Mode (Simulation)")
    print("=" * 60)
    
    wallet = "3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb"
    
    print(f"\nMonitoring wallet: {wallet}")
    print("This would continuously check for incoming USDG")
    print("\nIn production, you would:")
    print("  1. Set up a monitoring loop")
    print("  2. Check USDG balance periodically")
    print("  3. Trigger auto-sweep when threshold is exceeded")
    print("  4. Log all transactions for audit trail")
    
    # Simulated monitoring
    import time
    print("\nSimulating 3 checks...")
    for i in range(3):
        balance = get_usdg_balance(wallet, network="mainnet")
        print(f"  Check {i+1}: Balance = {balance} USDG")
        time.sleep(0.1)  # Short delay for demo
    
    print("\nMonitoring complete")


def example_gas_optimization():
    """Example 6: Gas optimization settings."""
    print("\n" + "=" * 60)
    print("Example 6: Gas Optimization Settings")
    print("=" * 60)
    
    # Different configuration options for gas optimization
    configs = [
        {
            "name": "Low Cost",
            "priority_fee": 100,
            "compute_units": 200000,
        },
        {
            "name": "Standard",
            "priority_fee": 1000,
            "compute_units": 150000,
        },
        {
            "name": "Fast (Jito)",
            "priority_fee": 5000,
            "compute_units": 100000,
            "use_jito": True,
        },
    ]
    
    print("\nGas optimization profiles:")
    for cfg in configs:
        print(f"\n  {cfg['name']}:")
        print(f"    Priority Fee: {cfg['priority_fee']} micro lamports")
        print(f"    Compute Units: {cfg['compute_units']}")
        if cfg.get("use_jito"):
            print(f"    Jito Tips: Enabled (for faster confirmation)")


def main():
    """Main entry point for example script."""
    parser = argparse.ArgumentParser(description="USDG Auto-Claim Examples")
    parser.add_argument(
        "--wallet", "-w",
        default="3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb",
        help="Wallet public key"
    )
    parser.add_argument(
        "--treasury", "-t",
        default=DEFAULT_TREASURY,
        help="Treasury address for auto-sweep"
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
        help="Run specific example (1-6)"
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON"
    )
    
    args = parser.parse_args()
    
    # Run examples
    if args.example:
        if args.example == 1:
            result = example_check_balance()
        elif args.example == 2:
            result = example_config_and_claimer()
        elif args.example == 3:
            result = example_check_claimable()
        elif args.example == 4:
            result = example_auto_sweep()
        elif args.example == 5:
            result = example_monitor_mode()
        elif args.example == 6:
            result = example_gas_optimization()
        else:
            print(f"Unknown example: {args.example}")
            sys.exit(1)
        
        if args.json and isinstance(result, (int, float, dict)):
            print("\n" + json.dumps(result if isinstance(result, dict) else {"result": result}, indent=2))
    else:
        # Run all examples
        example_check_balance()
        example_config_and_claimer()
        example_check_claimable()
        example_auto_sweep()
        example_monitor_mode()
        example_gas_optimization()
        
        print("\n" + "=" * 60)
        print("All examples completed!")
        print("=" * 60)


if __name__ == "__main__":
    main()
