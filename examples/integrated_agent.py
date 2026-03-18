"""
Integrated Agent Example
=========================

This example demonstrates how an autonomous agent would use all three modules
together in a realistic workflow:

1. Check wallet balances (agent_wallet.py)
2. Participate in DAO governance (dao_integration.py) 
3. Auto-sweep funds to treasury (usdg_auto_claim.py)

The agent autonomously manages its wallet, participates in governance decisions,
and ensures funds are efficiently moved to treasury when thresholds are met.

Run with: python examples/integrated_agent.py
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from solders.pubkey import Pubkey  # type: ignore[import-untyped]

# Import all modules
from agent_wallet import (
    agent_wallet_status,
    get_transaction_history,
    jupiter_quote,
    jupiter_swap,
)
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
from usdg_auto_claim import (
    check_claimable,
    execute_sweep,
    ClaimConfig,
    MonitorStats,
)


# =============================================================================
# Agent Configuration
# =============================================================================
@dataclass
class AgentConfig:
    """Configuration for the autonomous agent."""
    
    # Wallet
    agent_wallet: str = "3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb"
    treasury_wallet: str = "TreasuryWallet12345678901234567890123456789012"
    
    # Networks
    network: str = "mainnet"
    
    # Thresholds
    usdg_sweep_threshold: float = 1.0  # USDG
    min_sol_balance: float = 0.01  # SOL
    
    # Governance
    target_dao: str = "GqTswD7sV2xJ5xR4Qf5hZ6k8Lm9pN0wX2Y3zA4B5cD6E7f8G"
    auto_vote_enabled: bool = True
    vote_threshold: float = 0.6  # 60% for/against
    
    # Monitoring
    check_interval_seconds: int = 60
    proposal_check_interval: int = 300  # 5 minutes


# =============================================================================
# Agent State
# =============================================================================
@dataclass
class AgentState:
    """Current state of the autonomous agent."""
    
    config: AgentConfig
    sol_balance: float = 0.0
    usdg_balance: float = 0.0
    usdc_balance: float = 0.0
    proposals_voted: list = field(default_factory=list)
    sweeps_executed: int = 0
    last_check: datetime = field(default_factory=datetime.now)
    errors: list = field(default_factory=list)
    
    def add_error(self, error: str):
        """Record an error."""
        self.errors.append(f"[{datetime.now().isoformat()}] {error}")
        if len(self.errors) > 10:
            self.errors = self.errors[-10:]


# =============================================================================
# Autonomous Agent Class
# =============================================================================
class AutonomousAgent:
    """
    An autonomous agent that manages wallet, participates in DAO governance,
    and sweeps funds to treasury.
    """
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.state = AgentState(config=config)
        
    def log(self, message: str):
        """Log agent activity."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] AGENT: {message}")
    
    # -------------------------------------------------------------------------
    # Wallet Management
    # -------------------------------------------------------------------------
    def check_wallet_status(self):
        """Check and update wallet balances."""
        self.log("Checking wallet status...")
        
        try:
            status = agent_wallet_status(
                wallet=self.config.agent_wallet,
                network=self.config.network,
            )
            
            self.state.sol_balance = status.sol_balance
            
            # Extract token balances
            for token in status.tokens:
                if hasattr(token, 'symbol'):
                    if token.symbol == 'USDG':
                        self.state.usdg_balance = token.balance
                    elif token.symbol == 'USDC':
                        self.state.usdc_balance = token.balance
            
            self.log(f"Balances - SOL: {self.state.sol_balance:.4f}, "
                    f"USDG: {self.state.usdg_balance:.2f}, "
                    f"USDC: {self.state.usdc_balance:.2f}")
            
        except Exception as e:
            self.state.add_error(f"Wallet check failed: {e}")
            self.log(f"ERROR: Wallet check failed: {e}")
    
    def get_recent_transactions(self, limit: int = 5):
        """Get recent transaction history."""
        self.log(f"Fetching {limit} recent transactions...")
        
        try:
            txs = get_transaction_history(
                wallet=self.config.agent_wallet,
                network=self.config.network,
                limit=limit,
            )
            
            self.log(f"Found {len(txs)} transactions")
            for tx in txs:
                status = "OK" if tx.success else "FAIL"
                self.log(f"  [{status}] {tx.signature[:32]}... (fee: {tx.fee})")
                
        except Exception as e:
            self.state.add_error(f"Transaction history failed: {e}")
            self.log(f"ERROR: Transaction history failed: {e}")
    
    def get_swap_quote(self, from_token: str, to_token: str, amount: float):
        """Get a Jupiter swap quote."""
        self.log(f"Getting {from_token} -> {to_token} quote for {amount}...")
        
        try:
            quote = jupiter_quote(from_token, to_token, amount)
            self.log(f"Quote: {amount} {from_token} = {quote.output_amount} {to_token}")
            return quote
        except Exception as e:
            self.state.add_error(f"Swap quote failed: {e}")
            self.log(f"ERROR: Swap quote failed: {e}")
            return None
    
    # -------------------------------------------------------------------------
    # DAO Governance
    # -------------------------------------------------------------------------
    def check_dao_status(self):
        """Check DAO information and active proposals."""
        self.log("Checking DAO status...")
        
        try:
            # Get DAO info
            dao = get_dao_info(self.config.target_dao, self.config.network)
            if dao:
                self.log(f"Connected to DAO: {dao.name}")
            
            # Get voting power
            power = get_voting_power(
                self.config.target_dao,
                self.config.agent_wallet
            )
            self.log(f"Voting power: {power.power}")
            
            # Get active proposals
            proposals = get_active_proposals(self.config.target_dao)
            self.log(f"Active proposals: {len(proposals)}")
            
            for proposal in proposals:
                self.log(f"  - {proposal.title} ({proposal.status.value})")
            
            return dao, proposals
            
        except Exception as e:
            self.state.add_error(f"DAO check failed: {e}")
            self.log(f"ERROR: DAO check failed: {e}")
            return None, []
    
    def create_proposal(self, dao, title: str, description: str):
        """Create a new DAO proposal."""
        self.log(f"Creating proposal: {title}")
        
        try:
            proposal = create_proposal(
                dao=dao,
                title=title,
                description=description,
                proposer_wallet=self.config.agent_wallet,
                vote_period_hours=72,
            )
            
            self.log(f"Proposal created: {proposal.pubkey[:32]}...")
            return proposal
            
        except Exception as e:
            self.state.add_error(f"Proposal creation failed: {e}")
            self.log(f"ERROR: Proposal creation failed: {e}")
            return None
    
    def vote_on_proposal(self, proposal_pubkey: str, choice: VoteChoice):
        """Vote on a proposal."""
        self.log(f"Voting on proposal: {proposal_pubkey[:32]}...")
        
        try:
            vote = cast_vote(
                proposal_pubkey=proposal_pubkey,
                voter_wallet=self.config.agent_wallet,
                choice=choice,
            )
            
            self.log(f"Vote cast: {choice.value} ({vote.weight} weight)")
            self.state.proposals_voted.append(proposal_pubkey)
            return vote
            
        except Exception as e:
            self.state.add_error(f"Voting failed: {e}")
            self.log(f"ERROR: Voting failed: {e}")
            return None
    
    def auto_vote(self, proposals: list):
        """Automatically vote on proposals based on criteria."""
        if not self.config.auto_vote_enabled:
            self.log("Auto-vote disabled")
            return
        
        for proposal in proposals:
            if proposal.pubkey in self.state.proposals_voted:
                continue
            
            # Check proposal status
            status = get_proposal_status(proposal.pubkey)
            
            # Simple voting logic: vote FOR if quorum not reached yet
            if status.status == ProposalStatus.VOTING:
                total = status.votes_for + status.votes_against + status.votes_abstain
                if total > 0:
                    for_ratio = status.votes_for / total
                    if for_ratio >= self.config.vote_threshold:
                        self.vote_on_proposal(proposal.pubkey, VoteChoice.FOR)
                    else:
                        self.vote_on_proposal(proposal.pubkey, VoteChoice.ABSTAIN)
    
    # -------------------------------------------------------------------------
    # Treasury Management (USDG Auto-Sweep)
    # -------------------------------------------------------------------------
    async def check_usdg_balance(self):
        """Check USDG balance for sweep eligibility."""
        self.log("Checking USDG balance...")
        
        try:
            config = ClaimConfig(
                network=self.config.network,
                threshold_lamports=int(self.config.usdg_sweep_threshold * 1_000_000),
                min_sol_balance=int(self.config.min_sol_balance * 1e9),
            )
            
            wallet = Pubkey.from_string(self.config.agent_wallet)
            claim = await check_claimable(wallet, config)
            
            self.log(f"USDG Balance: {claim.balance_human:.2f} (threshold: {self.config.usdg_sweep_threshold})")
            self.log(f"Can sweep: {claim.can_sweep}")
            
            return claim
            
        except Exception as e:
            self.state.add_error(f"USDG check failed: {e}")
            self.log(f"ERROR: USDG check failed: {e}")
            return None
    
    async def sweep_to_treasury(self, keypair, treasury):
        """Execute sweep to treasury (requires keypair - demo only)."""
        self.log("Executing treasury sweep...")
        
        # Note: This would require an actual keypair to execute
        # For demo purposes, we just log what would happen
        self.log("TREASURY SWEEP would execute here")
        self.log(f"  From: {self.config.agent_wallet[:20]}...")
        self.log(f"  To: {self.config.treasury_wallet[:20]}...")
        
        self.state.sweeps_executed += 1
        self.log(f"Sweeps executed: {self.state.sweeps_executed}")
    
    # -------------------------------------------------------------------------
    # Main Agent Loop
    # -------------------------------------------------------------------------
    async def run_cycle(self):
        """Run one complete agent cycle."""
        self.log("=" * 50)
        self.log("Starting agent cycle")
        self.log("=" * 50)
        
        # Step 1: Wallet Management
        self.check_wallet_status()
        self.get_recent_transactions(limit=3)
        
        # Get swap quote as example
        if self.state.sol_balance > 0.1:
            self.get_swap_quote("SOL", "USDC", 0.1)
        
        # Step 2: DAO Governance
        dao, proposals = self.check_dao_status()
        
        # Auto-vote on active proposals
        if dao and proposals:
            self.auto_vote(proposals)
        
        # Step 3: USDG Auto-Sweep
        claim = await self.check_usdg_balance()
        
        # Update last check time
        self.state.last_check = datetime.now()
        
        self.log("Agent cycle completed")
    
    async def run_continuously(self, cycles: int = 3):
        """Run agent for a specified number of cycles."""
        self.log(f"Starting autonomous agent for {cycles} cycles")
        
        for i in range(cycles):
            self.log(f"\n{'#' * 50}")
            self.log(f"CYCLE {i + 1} of {cycles}")
            self.log(f"{'#' * 50}")
            
            await self.run_cycle()
            
            if i < cycles - 1:
                self.log(f"Waiting {self.config.check_interval_seconds}s...")
                await asyncio.sleep(self.config.check_interval_seconds)
        
        self.log("\n" + "=" * 50)
        self.log("Agent Summary")
        self.log("=" * 50)
        self.log(f"Total sweeps: {self.state.sweeps_executed}")
        self.log(f"Proposals voted: {len(self.state.proposals_voted)}")
        if self.state.errors:
            self.log(f"Errors: {len(self.state.errors)}")
            for err in self.state.errors:
                self.log(f"  - {err}")


# =============================================================================
# Main Entry Point
# =============================================================================
async def main():
    """Run the integrated autonomous agent example."""
    print("=" * 60)
    print("Autonomous Agent - Integrated Example")
    print("=" * 60)
    print()
    print("This example demonstrates an autonomous agent that:")
    print("1. Manages wallet (checks balances, tx history, swaps)")
    print("2. Participates in DAO governance (votes on proposals)")
    print("3. Sweeps USDG to treasury when thresholds are met")
    print()
    
    # Create agent configuration
    config = AgentConfig(
        agent_wallet="3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb",
        treasury_wallet="TreasuryWallet12345678901234567890123456789012",
        network="mainnet",
        usdg_sweep_threshold=1.0,
        min_sol_balance=0.01,
        auto_vote_enabled=True,
    )
    
    # Create and run agent
    agent = AutonomousAgent(config)
    
    # Run for 2 cycles (demo)
    await agent.run_continuously(cycles=2)
    
    print("\n" + "=" * 60)
    print("Integrated agent example completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
