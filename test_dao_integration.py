"""
Comprehensive tests for dao_integration.py
15+ pytest tests covering DAO operations, proposals, voting,
voting power, status tracking, and event listening.
"""

import json
import time
import pytest
from unittest.mock import patch, MagicMock

from dao_integration import (
    # Enums
    ProposalStatus,
    VoteChoice,
    # Data classes
    DAOInfo,
    Proposal,
    Vote,
    VotingPower,
    ProposalStatusResult,
    DAOOperationResult,
    # Exceptions
    DAOOperationError,
    # Functions
    get_dao_info,
    list_daos,
    search_daos,
    create_proposal,
    create_proposal_safe,
    get_voting_power,
    cast_vote,
    cast_vote_safe,
    get_proposal_status,
    get_proposal_status_safe,
    get_proposal_votes,
    get_active_proposals,
    listen_proposal_events,
    ProposalEventListener,
    get_agent_collective_votes,
    calculate_collective_vote,
    # Constants
    GOVERNANCE_PROGRAMS,
    KNOWN_DAOS_MAINNET,
    DEFAULT_AGENT_WALLET,
)


# ── 1. DAOInfo dataclass ─────────────────────────────────────────────────

def test_dao_info_creation():
    dao = DAOInfo(
        name="Test DAO",
        address="GqTswD7sV2xJ5xR4Qf5hZ6k8Lm9pN0wX2Y3zA4B5cD6E7f8G",
        realm="test_realm",
        governance_program_id="GovHQ5R1f4h7T3wK6z9X2Y5mN8pQ1rS4tU7vW9xY0zA3bC",
        is_active=True,
    )
    assert dao.name == "Test DAO"
    assert dao.is_active is True


def test_dao_info_to_dict():
    dao = DAOInfo(
        name="Test DAO",
        address="addr123",
        realm="realm123",
        governance_program_id="prog123",
    )
    d = dao.to_dict()
    assert d["name"] == "Test DAO"
    assert d["address"] == "addr123"


def test_dao_info_to_json():
    dao = DAOInfo(name="JSON DAO", address="addr", realm="r", governance_program_id="p")
    j = json.loads(dao.to_json())
    assert j["name"] == "JSON DAO"


# ── 2. Proposal dataclass ────────────────────────────────────────────────

def test_proposal_creation():
    proposal = Proposal(
        title="Test Proposal",
        description="This is a test proposal description",
        pubkey="proposal_pubkey_123",
        status=ProposalStatus.VOTING,
        proposer="proposer_wallet_456",
        dao_address="dao_address_789",
        voting_power_used=100.0,
        created_at=time.time(),
    )
    assert proposal.title == "Test Proposal"
    assert proposal.status == ProposalStatus.VOTING


def test_proposal_to_dict():
    proposal = Proposal(
        title="Dict Proposal",
        description="Description here",
        pubkey="pk",
        status=ProposalStatus.EXECUTED,
        proposer="p",
        dao_address="d",
        voting_power_used=50.0,
        created_at=1000.0,
    )
    d = proposal.to_dict()
    assert d["title"] == "Dict Proposal"
    assert d["status"] == "executed"


def test_proposal_to_json():
    proposal = Proposal(
        title="JSON Proposal",
        description="Desc",
        pubkey="pk",
        status=ProposalStatus.CANCELLED,
        proposer="p",
        dao_address="d",
        voting_power_used=25.0,
        created_at=2000.0,
    )
    j = json.loads(proposal.to_json())
    assert j["status"] == "cancelled"


def test_proposal_summary():
    proposal = Proposal(
        title="Summary Test",
        description="Desc",
        pubkey="pk",
        status=ProposalStatus.VOTING,
        proposer="proposer_wallet_address_12345",
        dao_address="dao",
        voting_power_used=75.0,
        created_at=time.time(),
        vote_end=time.time() + 86400,
    )
    summary = proposal.summary()
    assert "Summary Test" in summary
    assert "voting" in summary


# ── 3. Vote dataclass ─────────────────────────────────────────────────────

def test_vote_creation():
    vote = Vote(
        proposal_pubkey="proposal_123",
        voter="voter_wallet_456",
        choice=VoteChoice.FOR,
        weight=100.0,
        timestamp=time.time(),
    )
    assert vote.choice == VoteChoice.FOR
    assert vote.weight == 100.0


def test_vote_to_dict():
    vote = Vote(
        proposal_pubkey="p",
        voter="v",
        choice=VoteChoice.AGAINST,
        weight=50.0,
        timestamp=1000.0,
    )
    d = vote.to_dict()
    assert d["choice"] == "against"
    assert d["weight"] == 50.0


def test_vote_to_json():
    vote = Vote(
        proposal_pubkey="p",
        voter="v",
        choice=VoteChoice.ABSTAIN,
        weight=25.0,
        timestamp=2000.0,
    )
    j = json.loads(vote.to_json())
    assert j["choice"] == "abstain"


# ── 4. VotingPower dataclass ─────────────────────────────────────────────

def test_voting_power_creation():
    vp = VotingPower(
        wallet="wallet_123",
        dao_address="dao_456",
        power=500.0,
        last_update=time.time(),
    )
    assert vp.power == 500.0


def test_voting_power_to_dict():
    vp = VotingPower(wallet="w", dao_address="d", power=100.0, last_update=1000.0)
    d = vp.to_dict()
    assert d["power"] == 100.0


def test_voting_power_to_json():
    vp = VotingPower(wallet="w", dao_address="d", power=200.0, last_update=2000.0)
    j = json.loads(vp.to_json())
    assert j["power"] == 200.0


# ── 5. ProposalStatusResult dataclass ────────────────────────────────────

def test_proposal_status_result_creation():
    psr = ProposalStatusResult(
        pubkey="proposal_123",
        status=ProposalStatus.VOTING,
        votes_for=100.0,
        votes_against=50.0,
        votes_abstain=10.0,
        total_votes=160.0,
        quorum_reached=True,
        timestamp=time.time(),
    )
    assert psr.quorum_reached is True
    assert psr.total_votes == 160.0


def test_proposal_status_result_to_dict():
    psr = ProposalStatusResult(
        pubkey="p",
        status=ProposalStatus.EXECUTED,
        votes_for=100.0,
        votes_against=0.0,
        votes_abstain=0.0,
        total_votes=100.0,
        quorum_reached=True,
        timestamp=1000.0,
    )
    d = psr.to_dict()
    assert d["status"] == "executed"


# ── 6. DAOOperationResult dataclass ──────────────────────────────────────

def test_dao_operation_result_success():
    dao = DAOInfo(name="Test", address="a", realm="r", governance_program_id="p")
    result = DAOOperationResult(success=True, data=dao, transaction_signature="sig_123")
    assert result.success is True
    assert result.transaction_signature == "sig_123"


def test_dao_operation_result_failure():
    result = DAOOperationResult(success=False, error="Something went wrong")
    assert result.success is False
    assert result.error == "Something went wrong"


def test_dao_operation_result_to_dict():
    result = DAOOperationResult(success=True, error=None)
    d = result.to_dict()
    assert d["success"] is True


# ── 7. DAO Discovery Functions ───────────────────────────────────────────

def test_get_dao_info_valid_address():
    dao = get_dao_info("GqTswD7sV2xJ5xR4Qf5hZ6k8Lm9pN0wX2Y3zA4B5cD6E7f8G")
    assert dao is not None
    assert dao.name == "Realms DAO"
    assert dao.is_active is True


def test_get_dao_info_unknown_address():
    dao = get_dao_info("UnknownAddress123456789012345678901234567890")
    assert dao is not None
    assert "DAO-" in dao.name


def test_get_dao_info_invalid_address():
    dao = get_dao_info("short")
    assert dao is None


def test_list_daos_mainnet():
    daos = list_daos("mainnet")
    assert len(daos) > 0
    assert all(isinstance(d, DAOInfo) for d in daos)


def test_list_daos_devnet():
    daos = list_daos("devnet")
    assert isinstance(daos, list)


def test_search_daos():
    daos = search_daos("Realms", "mainnet")
    assert isinstance(daos, list)


# ── 8. Proposal Creation ─────────────────────────────────────────────────

def test_create_proposal_valid():
    dao = DAOInfo(
        name="Test DAO",
        address="GqTswD7sV2xJ5xR4Qf5hZ6k8Lm9pN0wX2Y3zA4B5cD6E7f8G",
        realm="realm",
        governance_program_id="prog",
    )
    proposal = create_proposal(
        dao=dao,
        title="Valid Proposal Title",
        description="This is a valid proposal description with enough text",
        proposer_wallet="3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb",
    )
    assert proposal.title == "Valid Proposal Title"
    assert proposal.status == ProposalStatus.VOTING


def test_create_proposal_short_title():
    dao = DAOInfo(
        name="Test DAO",
        address="GqTswD7sV2xJ5xR4Qf5hZ6k8Lm9pN0wX2Y3zA4B5cD6E7f8G",
        realm="realm",
        governance_program_id="prog",
    )
    with pytest.raises(DAOOperationError, match="title must be at least"):
        create_proposal(
            dao=dao,
            title="AB",  # Too short
            description="Valid description",
            proposer_wallet="3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb",
        )


def test_create_proposal_short_description():
    dao = DAOInfo(
        name="Test DAO",
        address="GqTswD7sV2xJ5xR4Qf5hZ6k8Lm9pN0wX2Y3zA4B5cD6E7f8G",
        realm="realm",
        governance_program_id="prog",
    )
    with pytest.raises(DAOOperationError, match="description must be at least"):
        create_proposal(
            dao=dao,
            title="Valid Title",
            description="Short",  # Too short
            proposer_wallet="3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb",
        )


def test_create_proposal_invalid_wallet():
    dao = DAOInfo(
        name="Test DAO",
        address="GqTswD7sV2xJ5xR4Qf5hZ6k8Lm9pN0wX2Y3zA4B5cD6E7f8G",
        realm="realm",
        governance_program_id="prog",
    )
    with pytest.raises(DAOOperationError, match="Invalid proposer wallet"):
        create_proposal(
            dao=dao,
            title="Valid Title",
            description="Valid description",
            proposer_wallet="short",
        )


def test_create_proposal_safe_success():
    dao = DAOInfo(
        name="Test DAO",
        address="GqTswD7sV2xJ5xR4Qf5hZ6k8Lm9pN0wX2Y3zA4B5cD6E7f8G",
        realm="realm",
        governance_program_id="prog",
    )
    result = create_proposal_safe(
        dao=dao,
        title="Safe Proposal",
        description="This is a safe proposal description",
        proposer_wallet="3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb",
    )
    assert result.success is True
    assert isinstance(result.data, Proposal)
    assert result.transaction_signature is not None


def test_create_proposal_safe_failure():
    dao = DAOInfo(name="Test", address="a", realm="r", governance_program_id="p")
    result = create_proposal_safe(
        dao=dao,
        title="AB",  # Invalid
        description="Short",
        proposer_wallet="short",
    )
    assert result.success is False
    assert result.error is not None


# ── 9. Voting Power ───────────────────────────────────────────────────────

def test_get_voting_power_valid():
    power = get_voting_power(
        "GqTswD7sV2xJ5xR4Qf5hZ6k8Lm9pN0wX2Y3zA4B5cD6E7f8G",
        "3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb",
    )
    assert power.power > 0
    assert power.wallet == "3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb"


def test_get_voting_power_invalid_dao():
    power = get_voting_power("short", "3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb")
    assert power.power == 0


def test_get_voting_power_invalid_wallet():
    power = get_voting_power("GqTswD7sV2xJ5xR4Qf5hZ6k8Lm9pN0wX2Y3zA4B5cD6E7f8G", "short")
    assert power.power == 0


# ── 10. Vote Casting ─────────────────────────────────────────────────────

def test_cast_vote_valid():
    vote = cast_vote(
        proposal_pubkey="proposal_pubkey_123456789012345678901234567890",
        voter_wallet="3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb",
        choice=VoteChoice.FOR,
        weight=100.0,
    )
    assert vote.choice == VoteChoice.FOR
    assert vote.weight == 100.0


def test_cast_vote_invalid_proposal():
    with pytest.raises(DAOOperationError, match="Invalid proposal"):
        cast_vote(
            proposal_pubkey="short",
            voter_wallet="3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb",
            choice=VoteChoice.FOR,
        )


def test_cast_vote_invalid_wallet():
    with pytest.raises(DAOOperationError, match="Invalid voter"):
        cast_vote(
            proposal_pubkey="proposal_pubkey_123456789012345678901234567890",
            voter_wallet="short",
            choice=VoteChoice.AGAINST,
        )


def test_cast_vote_invalid_choice():
    with pytest.raises(DAOOperationError, match="Invalid vote choice"):
        cast_vote(
            proposal_pubkey="proposal_pubkey_123456789012345678901234567890",
            voter_wallet="3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb",
            choice="invalid",
        )


def test_cast_vote_negative_weight():
    with pytest.raises(DAOOperationError, match="weight must be positive"):
        cast_vote(
            proposal_pubkey="proposal_pubkey_123456789012345678901234567890",
            voter_wallet="3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb",
            choice=VoteChoice.ABSTAIN,
            weight=-10.0,
        )


def test_cast_vote_safe_success():
    result = cast_vote_safe(
        proposal_pubkey="proposal_pubkey_123456789012345678901234567890",
        voter_wallet="3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb",
        choice=VoteChoice.FOR,
        weight=50.0,
    )
    assert result.success is True
    assert isinstance(result.data, Vote)


def test_cast_vote_safe_failure():
    result = cast_vote_safe(
        proposal_pubkey="short",
        voter_wallet="3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb",
        choice=VoteChoice.FOR,
    )
    assert result.success is False


# ── 11. Proposal Status ───────────────────────────────────────────────────

def test_get_proposal_status_valid():
    status = get_proposal_status("proposal_pubkey_123456789012345678901234567890")
    assert isinstance(status, ProposalStatusResult)
    assert status.pubkey is not None


def test_get_proposal_status_invalid():
    status = get_proposal_status("short")
    assert status.status == ProposalStatus.DRAFT
    assert status.votes_for == 0


def test_get_proposal_status_safe():
    result = get_proposal_status_safe("proposal_pubkey_123456789012345678901234567890")
    assert result.success is True
    assert isinstance(result.data, ProposalStatusResult)


# ── 12. Proposal Votes ───────────────────────────────────────────────────

def test_get_proposal_votes_valid():
    votes = get_proposal_votes("proposal_pubkey_123456789012345678901234567890")
    assert isinstance(votes, list)
    # All votes should have valid choices
    for vote in votes:
        assert isinstance(vote.choice, VoteChoice)


def test_get_proposal_votes_invalid():
    votes = get_proposal_votes("short")
    assert votes == []


# ── 13. Active Proposals ─────────────────────────────────────────────────

def test_get_active_proposals_valid():
    proposals = get_active_proposals("GqTswD7sV2xJ5xR4Qf5hZ6k8Lm9pN0wX2Y3zA4B5cD6E7f8G")
    assert isinstance(proposals, list)
    assert all(isinstance(p, Proposal) for p in proposals)


def test_get_active_proposals_invalid():
    proposals = get_active_proposals("short")
    assert proposals == []


# ── 14. Event Listening ──────────────────────────────────────────────────

def test_listen_proposal_events():
    events_received = []
    
    def callback(proposal, event_type):
        events_received.append((proposal, event_type))
    
    listener = listen_proposal_events(
        "GqTswD7sV2xJ5xR4Qf5hZ6k8Lm9pN0wX2Y3zA4B5cD6E7f8G",
        callback,
    )
    
    assert listener.is_running is True
    assert listener.dao_address == "GqTswD7sV2xJ5xR4Qf5hZ6k8Lm9pN0wX2Y3zA4B5cD6E7f8G"
    
    listener.stop()
    assert listener.is_running is False


def test_proposal_event_listener_poll():
    listener = ProposalEventListener(
        dao_address="GqTswD7sV2xJ5xR4Qf5hZ6k8Lm9pN0wX2Y3zA4B5cD6E7f8G",
        callback=lambda p, e: None,
    )
    # Poll when not running should return empty
    events = listener.poll_events()
    assert events == []


# ── 15. Agent Collective Functions ────────────────────────────────────────

def test_get_agent_collective_votes():
    wallets = [
        "3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb",
        "AnotherWallet123456789012345678901234567890",
    ]
    votes = get_agent_collective_votes(
        proposal_pubkey="proposal_pubkey_123456789012345678901234567890",
        agent_wallets=wallets,
        dao_address="GqTswD7sV2xJ5xR4Qf5hZ6k8Lm9pN0wX2Y3zA4B5cD6E7f8G",
    )
    assert len(votes) == 2
    assert all(isinstance(v, Vote) for v in votes.values())


def test_calculate_collective_vote_for():
    votes = {
        "w1": Vote("p", "w1", VoteChoice.FOR, 100.0, time.time()),
        "w2": Vote("p", "w2", VoteChoice.FOR, 50.0, time.time()),
        "w3": Vote("p", "w3", VoteChoice.AGAINST, 30.0, time.time()),
    }
    choice, total = calculate_collective_vote(votes)
    assert choice == VoteChoice.FOR
    assert total == 180.0


def test_calculate_collective_vote_against():
    votes = {
        "w1": Vote("p", "w1", VoteChoice.AGAINST, 100.0, time.time()),
        "w2": Vote("p", "w2", VoteChoice.FOR, 50.0, time.time()),
    }
    choice, total = calculate_collective_vote(votes)
    assert choice == VoteChoice.AGAINST


def test_calculate_collective_vote_empty():
    choice, total = calculate_collective_vote({})
    assert choice == VoteChoice.ABSTAIN
    assert total == 0


# ── 16. Constants ────────────────────────────────────────────────────────

def test_governance_programs():
    assert "realms" in GOVERNANCE_PROGRAMS
    assert "raydium" in GOVERNANCE_PROGRAMS
    assert "spl_governance" in GOVERNANCE_PROGRAMS


def test_known_daos_mainnet():
    assert len(KNOWN_DAOS_MAINNET) > 0
    assert all(isinstance(d, str) for d in KNOWN_DAOS_MAINNET)


def test_default_agent_wallet():
    assert DEFAULT_AGENT_WALLET == "3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb"


# ── 17. Enums ─────────────────────────────────────────────────────────────

def test_proposal_status_values():
    assert ProposalStatus.DRAFT.value == "draft"
    assert ProposalStatus.VOTING.value == "voting"
    assert ProposalStatus.EXECUTED.value == "executed"
    assert ProposalStatus.CANCELLED.value == "cancelled"
    assert ProposalStatus.EXPIRED.value == "expired"


def test_vote_choice_values():
    assert VoteChoice.FOR.value == "for"
    assert VoteChoice.AGAINST.value == "against"
    assert VoteChoice.ABSTAIN.value == "abstain"
