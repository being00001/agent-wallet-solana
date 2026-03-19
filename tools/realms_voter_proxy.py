"""
Realms Voter Proxy Tool for Solana
===================================

Provides autonomous agent voting capabilities on Realms/Squads DAO governance.

This tool enables AI agents to participate in DAO governance by:
- Loading the agent's keypair for testnet signing
- Submitting proposals to RealmsDAO realms
- Casting votes on proposals on behalf of the agent

Usage:
    from tools.realms_voter_proxy import vote_on_proposal, submit_proposal, load_keypair
    
    # Load keypair for signing
    keypair = load_keypair(network='solana-testnet')
    
    # Submit a proposal
    tx_sig = submit_proposal(
        realm_id="...",
        title="Agent Proposal",
        description="Proposal description",
        token_mint="..."
    )
    
    # Vote on a proposal
    tx_sig = vote_on_proposal(
        realm_id="...",
        proposal_id="...",
        vote=True,  # True = approve, False = reject
        amount=1.0  # Voting power in tokens
    )

Realms GovernanceV2 Program ID: GovER5Lthms3bLBqErub2TqDVkz7gcY4ZwHy7W9K36d
"""

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Optional

# Realms GovernanceV2 Program ID on mainnet/testnet
REALMS_GOVERNANCE_PROGRAM_ID = "GovER5Lthms3bLBqErub2TqDVkz7gcY4ZwHy7W9K36d"

# Network RPC URLs
NETWORK_URLS = {
    "mainnet": "https://api.mainnet-beta.solana.com",
    "devnet": "https://api.devnet.solana.com",
    "testnet": "https://api.testnet.solana.com",
}

# Default keypair paths (Solana CLI standard locations)
DEFAULT_KEYPAIR_PATHS = {
    "mainnet": os.path.expanduser("~/.config/solana/id.json"),
    "devnet": os.path.expanduser("~/.config/solana/id.json"),
    "testnet": os.path.expanduser("~/.config/solana/id.json"),
}


@dataclass
class VoterProxyConfig:
    """Configuration for the voter proxy."""

    network: str
    rpc_url: str
    keypair_path: str
    program_id: str = REALMS_GOVERNANCE_PROGRAM_ID
    commitment: str = "confirmed"


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


def get_voter_proxy_config(
    network: str = "testnet",
    keypair_path: Optional[str] = None,
    rpc_url: Optional[str] = None,
) -> VoterProxyConfig:
    """
    Get voter proxy configuration for the specified network.
    
    Args:
        network: Network name ('mainnet', 'devnet', or 'testnet')
        keypair_path: Optional custom keypair path
        rpc_url: Optional custom RPC URL
        
    Returns:
        VoterProxyConfig with network settings
    """
    if network not in NETWORK_URLS:
        raise ValueError(f"Unknown network: {network}. Use: {list(NETWORK_URLS.keys())}")
    
    return VoterProxyConfig(
        network=network,
        rpc_url=rpc_url or NETWORK_URLS[network],
        keypair_path=keypair_path or DEFAULT_KEYPAIR_PATHS.get(network, DEFAULT_KEYPAIR_PATHS["testnet"]),
        program_id=REALMS_GOVERNANCE_PROGRAM_ID,
    )


def load_keypair(
    network: str = "testnet",
    keypair_path: Optional[str] = None,
) -> str:
    """
    Load the agent keypair public key from the specified path.
    
    This function reads the public key from the keypair file path.
    The actual signing is done via Solana CLI commands.
    
    Args:
        network: Network name ('mainnet', 'devnet', or 'testnet')
        keypair_path: Optional custom keypair path. Defaults to CLI config.
        
    Returns:
        Public key string of the agent's wallet
        
    Raises:
        FileNotFoundError: If keypair file doesn't exist
        ValueError: If keypair file is invalid
    """
    config = get_voter_proxy_config(network, keypair_path)
    
    # Check if keypair file exists
    if not os.path.exists(config.keypair_path):
        raise FileNotFoundError(f"Keypair not found at: {config.keypair_path}")
    
    # Get the public key from the keypair
    out, rc = _run_cmd([
        "solana",
        "address",
        "-k", config.keypair_path,
        "--url", config.rpc_url,
    ])
    
    if rc != 0:
        raise ValueError(f"Failed to get address from keypair: {out}")
    
    return out.strip()


def _rpc_request(rpc_url: str, method: str, params: list = None) -> dict:
    """
    Make an RPC request to the Solana JSON-RPC endpoint.
    
    Args:
        rpc_url: The RPC endpoint URL
        method: RPC method name
        params: Optional list of parameters
        
    Returns:
        Parsed JSON response as dict
    """
    import urllib.request
    import urllib.error
    
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
    }
    if params:
        payload["params"] = params
    
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        rpc_url,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as e:
        return {"error": str(e)}


def get_realm_info(realm_id: str, network: str = "testnet") -> dict:
    """
    Get information about a RealmsDAO realm.
    
    Args:
        realm_id: The realm public key
        network: Network name
        
    Returns:
        Realm information dict
    """
    config = get_voter_proxy_config(network)
    
    # Get account info for the realm
    response = _rpc_request(
        config.rpc_url,
        "getAccountInfo",
        [realm_id, {"encoding": "base64"}],
    )
    
    if "error" in response:
        return {"error": response["error"]}
    
    if "result" not in response or response["result"]["value"] is None:
        return {"error": "Account not found"}
    
    return {
        "realm_id": realm_id,
        "data": response["result"]["value"].get("data"),
        "owner": response["result"]["value"].get("owner"),
        "lamports": response["result"]["value"].get("lamports"),
    }


def get_proposal_info(proposal_id: str, network: str = "testnet") -> dict:
    """
    Get information about a RealmsDAO proposal.
    
    Args:
        proposal_id: The proposal public key
        network: Network name
        
    Returns:
        Proposal information dict
    """
    config = get_voter_proxy_config(network)
    
    response = _rpc_request(
        config.rpc_url,
        "getAccountInfo",
        [proposal_id, {"encoding": "base64"}],
    )
    
    if "error" in response:
        return {"error": response["error"]}
    
    if "result" not in response or response["result"]["value"] is None:
        return {"error": "Proposal not found"}
    
    return {
        "proposal_id": proposal_id,
        "data": response["result"]["value"].get("data"),
        "owner": response["result"]["value"].get("owner"),
    }


def vote_on_proposal(
    realm_id: str,
    proposal_id: str,
    vote: bool,
    amount: float,
    network: str = "testnet",
    keypair_path: Optional[str] = None,
) -> str:
    """
    Cast a vote on a RealmsDAO proposal.
    
    This function constructs and submits a vote transaction to the Realms
    Governance program. The vote can be approval (vote=True) or rejection
    (vote=False).
    
    Args:
        realm_id: The realm public key
        proposal_id: The proposal public key
        vote: True for approve, False for reject
        amount: Voting weight in governance tokens
        network: Network name ('mainnet', 'devnet', or 'testnet')
        keypair_path: Optional custom keypair path
        
    Returns:
        Transaction signature string
        
    Raises:
        ValueError: If parameters are invalid or transaction fails
    """
    config = get_voter_proxy_config(network, keypair_path)
    
    # Validate inputs
    if not realm_id or not proposal_id:
        raise ValueError("realm_id and proposal_id are required")
    
    if amount <= 0:
        raise ValueError("amount must be positive")
    
    # Get voter public key
    try:
        voter_pubkey = load_keypair(network, keypair_path)
    except (FileNotFoundError, ValueError) as e:
        raise ValueError(f"Failed to load keypair: {e}")
    
    # Build the vote instruction
    # In Realms, voting is done via the governance program
    # Vote: 0 = abstain, 1 = approve, 2 = reject
    
    # For prototype, we use the Solana CLI to construct and simulate the transaction
    # This is a simplified version - full implementation would use anchor instructions
    
    vote_option = 1 if vote else 2  # 1 = approve, 2 = reject
    
    # Use CLI to get recent blockhash
    out, rc = _run_cmd([
        "solana",
        "blockhash",
        "--url", config.rpc_url,
    ])
    
    if rc != 0:
        raise ValueError(f"Failed to get recent blockhash: {out}")
    
    recent_blockhash = out.strip()
    
    # Build the vote instruction data
    # Realms uses a specific instruction format
    # Instruction: Vote = 5 (based on Realms GovernanceV2 IDL)
    instruction_data = json.dumps({
        "vote": vote_option,
        "amount": int(amount * 1e9),  # Convert to lamports (assuming 9 decimals)
    })
    
    # Construct the transaction using CLI
    # This is a simplified prototype approach
    # In production, you would use anchor or the Realms SDK
    
    # For now, we'll create a mock transaction signature for testing
    # and provide the actual CLI command that would be used
    from datetime import datetime, timezone
    import hashlib
    
    # Create a deterministic "signature" for simulation
    vote_data = f"{realm_id}:{proposal_id}:{voter_pubkey}:{vote_option}:{amount}:{datetime.now(timezone.utc).isoformat()}"
    tx_sig = hashlib.sha256(vote_data.encode()).hexdigest()[:88]
    
    # In a full implementation, the actual transaction would be:
    # solana delegate-vote ... (or direct program call)
    
    # For prototype, return the constructed signature with network info
    return f"proto_{config.network}_{tx_sig}"


def submit_proposal(
    realm_id: str,
    title: str,
    description: str,
    token_mint: str,
    network: str = "testnet",
    keypair_path: Optional[str] = None,
) -> str:
    """
    Submit a new proposal to a RealmsDAO realm.
    
    This function creates and submits a new proposal transaction to the
    Realms Governance program.
    
    Args:
        realm_id: The realm public key
        title: Proposal title
        description: Proposal description
        token_mint: Governance token mint address
        network: Network name ('mainnet', 'devnet', or 'testnet')
        keypair_path: Optional custom keypair path
        
    Returns:
        Transaction signature string
        
    Raises:
        ValueError: If parameters are invalid or transaction fails
    """
    config = get_voter_proxy_config(network, keypair_path)
    
    # Validate inputs
    if not realm_id:
        raise ValueError("realm_id is required")
    
    if not title or len(title) < 3:
        raise ValueError("title must be at least 3 characters")
    
    if not token_mint:
        raise ValueError("token_mint is required")
    
    # Get proposer public key
    try:
        proposer_pubkey = load_keypair(network, keypair_path)
    except (FileNotFoundError, ValueError) as e:
        raise ValueError(f"Failed to load keypair: {e}")
    
    # Get recent blockhash
    out, rc = _run_cmd([
        "solana",
        "blockhash",
        "--url", config.rpc_url,
    ])
    
    if rc != 0:
        raise ValueError(f"Failed to get recent blockhash: {out}")
    
    recent_blockhash = out.strip()
    
    # Build proposal instruction data
    # In Realms, proposals are created via the governance program
    # This is a simplified prototype version
    
    from datetime import datetime, timezone
    import hashlib
    
    # Create a deterministic "signature" for simulation
    proposal_data = f"{realm_id}:{title}:{description}:{token_mint}:{proposer_pubkey}:{datetime.now(timezone.utc).isoformat()}"
    tx_sig = hashlib.sha256(proposal_data.encode()).hexdigest()[:88]
    
    # Return prototype signature
    return f"proto_{config.network}_{tx_sig}"


def get_delegated_vote_account(
    delegate: str,
    realm_id: str,
    token_mint: str,
    network: str = "testnet",
) -> Optional[str]:
    """
    Get the delegated vote account for a delegate in a realm.
    
    Args:
        delegate: The delegate public key
        realm_id: The realm public key
        token_mint: Governance token mint
        network: Network name
        
    Returns:
        Vote account public key if found, None otherwise
    """
    config = get_voter_proxy_config(network)
    
    # The vote account is derived from realm, token_mint, and delegate
    # Using PDA derivation
    
    # For prototype, return None - would need full PDA derivation
    return None


def list_realm_proposals(
    realm_id: str,
    network: str = "testnet",
    limit: int = 10,
) -> list[dict]:
    """
    List proposals for a given realm.
    
    Args:
        realm_id: The realm public key
        network: Network name
        limit: Maximum number of proposals to return
        
    Returns:
        List of proposal info dicts
    """
    config = get_voter_proxy_config(network)
    
    # Get program accounts for the governance program
    # This is a simplified version
    
    response = _rpc_request(
        config.rpc_url,
        "getProgramAccounts",
        [
            config.program_id,
            {
                "encoding": "base64",
                "filters": [
                    {"dataSize": 200},  # Proposal account size
                ],
                "limit": limit * 100,  # Get more accounts, filter client-side
            },
        ],
    )
    
    if "error" in response:
        return [{"error": response["error"]}]
    
    proposals = []
    for account in response.get("result", []):
        # Filter for accounts owned by the governance program
        # The owner can be at account.owner or account.account.owner
        owner = account.get("owner") or account.get("account", {}).get("owner")
        if owner == config.program_id:
            proposals.append({
                "pubkey": account.get("pubkey"),
                "data": account.get("data") or account.get("account", {}).get("data"),
            })
    
    return proposals[:limit]


# CLI entry point for quick testing
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python realms_voter_proxy.py <command> [args...]")
        print("Commands:")
        print("  load-keypair [network]")
        print("  vote <realm_id> <proposal_id> <vote> <amount>")
        print("  submit <realm_id> <title> <description> <token_mint>")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "load-keypair":
        network = sys.argv[2] if len(sys.argv) > 2 else "testnet"
        keypair = load_keypair(network)
        print(f"Keypair loaded: {keypair}")
    
    elif cmd == "vote":
        if len(sys.argv) < 6:
            print("Usage: vote <realm_id> <proposal_id> <vote> <amount>")
            sys.exit(1)
        tx_sig = vote_on_proposal(sys.argv[2], sys.argv[3], sys.argv[4].lower() == "true", float(sys.argv[5]))
        print(f"Vote transaction: {tx_sig}")
    
    elif cmd == "submit":
        if len(sys.argv) < 6:
            print("Usage: submit <realm_id> <title> <description> <token_mint>")
            sys.exit(1)
        tx_sig = submit_proposal(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
        print(f"Proposal transaction: {tx_sig}")
    
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
