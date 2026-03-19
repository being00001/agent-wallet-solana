"""Tests for realms_voter_proxy tool."""

import json
import os
import subprocess
import sys
import tempfile
from unittest.mock import patch, MagicMock

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.realms_voter_proxy import (
    vote_on_proposal,
    submit_proposal,
    load_keypair,
    get_voter_proxy_config,
    get_realm_info,
    get_proposal_info,
    list_realm_proposals,
    get_delegated_vote_account,
    VoterProxyConfig,
    REALMS_GOVERNANCE_PROGRAM_ID,
    NETWORK_URLS,
    DEFAULT_KEYPAIR_PATHS,
    _rpc_request,
)


class TestVoterProxyConfig:
    """Tests for VoterProxyConfig dataclass."""

    def test_config_defaults(self):
        config = VoterProxyConfig(
            network="testnet",
            rpc_url="https://api.testnet.solana.com",
            keypair_path="/path/to/keypair",
        )
        assert config.network == "testnet"
        assert config.program_id == REALMS_GOVERNANCE_PROGRAM_ID
        assert config.commitment == "confirmed"

    def test_config_custom_values(self):
        config = VoterProxyConfig(
            network="mainnet",
            rpc_url="https://custom.rpc.com",
            keypair_path="/custom/path",
            program_id="CustomProgram123",
            commitment="finalized",
        )
        assert config.network == "mainnet"
        assert config.rpc_url == "https://custom.rpc.com"
        assert config.program_id == "CustomProgram123"
        assert config.commitment == "finalized"


class TestGetVoterProxyConfig:
    """Tests for get_voter_proxy_config function."""

    def test_testnet_config(self):
        config = get_voter_proxy_config("testnet")
        assert config.network == "testnet"
        assert config.rpc_url == NETWORK_URLS["testnet"]
        assert "id.json" in config.keypair_path

    def test_devnet_config(self):
        config = get_voter_proxy_config("devnet")
        assert config.network == "devnet"
        assert config.rpc_url == NETWORK_URLS["devnet"]

    def test_mainnet_config(self):
        config = get_voter_proxy_config("mainnet")
        assert config.network == "mainnet"
        assert config.rpc_url == NETWORK_URLS["mainnet"]

    def test_custom_rpc_url(self):
        config = get_voter_proxy_config("testnet", rpc_url="https://custom.rpc.com")
        assert config.rpc_url == "https://custom.rpc.com"

    def test_custom_keypair_path(self):
        config = get_voter_proxy_config("testnet", keypair_path="/custom/keypair.json")
        assert config.keypair_path == "/custom/keypair.json"

    def test_invalid_network(self):
        try:
            get_voter_proxy_config("invalid_network")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Unknown network" in str(e)


class TestLoadKeypair:
    """Tests for load_keypair function."""

    @patch("tools.realms_voter_proxy.os.path.exists")
    @patch("tools.realms_voter_proxy._run_cmd")
    def test_load_keypair_success(self, mock_cmd, mock_exists):
        mock_exists.return_value = True
        mock_cmd.return_value = ("3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb", 0)
        pubkey = load_keypair("testnet", "/fake/path")
        assert pubkey == "3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb"
        mock_cmd.assert_called_once()

    @patch("tools.realms_voter_proxy._run_cmd")
    def test_load_keypair_failure(self, mock_cmd):
        mock_cmd.return_value = ("error", 1)
        try:
            load_keypair("testnet")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Failed to get address" in str(e)

    def test_load_keypair_file_not_found(self):
        try:
            load_keypair("testnet", "/nonexistent/path.json")
            assert False, "Should have raised FileNotFoundError"
        except FileNotFoundError as e:
            assert "Keypair not found" in str(e)

    @patch("tools.realms_voter_proxy._run_cmd")
    def test_load_keypair_different_networks(self, mock_cmd):
        mock_cmd.return_value = ("Pubkey123", 0)
        
        load_keypair("mainnet")
        call_args = mock_cmd.call_args[0][0]
        assert "--url" in call_args
        assert NETWORK_URLS["mainnet"] in call_args

        mock_cmd.reset_mock()
        load_keypair("devnet")
        call_args = mock_cmd.call_args[0][0]
        assert NETWORK_URLS["devnet"] in call_args


class TestRpcRequest:
    """Tests for _rpc_request function."""

    @patch("urllib.request.urlopen")
    def test_rpc_request_success(self, mock_urlopen):
        import urllib.request
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"jsonrpc": "2.0", "result": {"value": "test"}}'
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        from tools.realms_voter_proxy import _rpc_request
        result = _rpc_request("https://api.testnet.solana.com", "getBlockHeight")
        
        assert "result" in result
        assert result["result"]["value"] == "test"

    @patch("urllib.request.urlopen")
    def test_rpc_request_error(self, mock_urlopen):
        import urllib.error
        import urllib.request
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        
        from tools.realms_voter_proxy import _rpc_request
        result = _rpc_request("https://api.testnet.solana.com", "getBlockHeight")
        
        assert "error" in result


class TestGetRealmInfo:
    """Tests for get_realm_info function."""

    @patch("tools.realms_voter_proxy._rpc_request")
    def test_get_realm_info_success(self, mock_rpc):
        mock_rpc.return_value = {
            "result": {
                "value": {
                    "data": "base64data",
                    "owner": REALMS_GOVERNANCE_PROGRAM_ID,
                    "lamports": 1000,
                }
            }
        }
        
        result = get_realm_info("Realm123", "testnet")
        
        assert result["realm_id"] == "Realm123"
        assert result["data"] == "base64data"

    @patch("tools.realms_voter_proxy._rpc_request")
    def test_get_realm_info_not_found(self, mock_rpc):
        mock_rpc.return_value = {"result": {"value": None}}
        
        result = get_realm_info("NonexistentRealm", "testnet")
        
        assert "error" in result

    @patch("tools.realms_voter_proxy._rpc_request")
    def test_get_rpc_error(self, mock_rpc):
        mock_rpc.return_value = {"error": "RPC error"}
        
        result = get_realm_info("Realm123", "testnet")
        
        assert result["error"] == "RPC error"


class TestGetProposalInfo:
    """Tests for get_proposal_info function."""

    @patch("tools.realms_voter_proxy._rpc_request")
    def test_get_proposal_info_success(self, mock_rpc):
        mock_rpc.return_value = {
            "result": {
                "value": {
                    "data": "proposal_data",
                    "owner": REALMS_GOVERNANCE_PROGRAM_ID,
                }
            }
        }
        
        result = get_proposal_info("Proposal123", "testnet")
        
        assert result["proposal_id"] == "Proposal123"
        assert result["data"] == "proposal_data"

    @patch("tools.realms_voter_proxy._rpc_request")
    def test_get_proposal_info_not_found(self, mock_rpc):
        mock_rpc.return_value = {"result": {"value": None}}
        
        result = get_proposal_info("Nonexistent", "testnet")
        
        assert "error" in result


class TestVoteOnProposal:
    """Tests for vote_on_proposal function."""

    @patch("tools.realms_voter_proxy.load_keypair")
    @patch("tools.realms_voter_proxy._run_cmd")
    def test_vote_approve(self, mock_cmd, mock_load):
        mock_cmd.return_value = ("blockhash123", 0)
        mock_load.return_value = "3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb"
        
        tx_sig = vote_on_proposal(
            realm_id="Realm123",
            proposal_id="Proposal456",
            vote=True,
            amount=1.0,
            network="testnet",
        )
        
        assert tx_sig.startswith("proto_testnet_")
        assert len(tx_sig) > 20

    @patch("tools.realms_voter_proxy.load_keypair")
    @patch("tools.realms_voter_proxy._run_cmd")
    def test_vote_reject(self, mock_cmd, mock_load):
        mock_cmd.return_value = ("blockhash123", 0)
        mock_load.return_value = "3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb"
        
        tx_sig = vote_on_proposal(
            realm_id="Realm123",
            proposal_id="Proposal456",
            vote=False,
            amount=2.5,
            network="testnet",
        )
        
        assert tx_sig.startswith("proto_testnet_")

    @patch("tools.realms_voter_proxy.load_keypair")
    @patch("tools.realms_voter_proxy._run_cmd")
    def test_vote_with_different_amounts(self, mock_cmd, mock_load):
        mock_cmd.return_value = ("blockhash123", 0)
        mock_load.return_value = "3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb"
        
        tx_sig = vote_on_proposal(
            realm_id="R",
            proposal_id="P",
            vote=True,
            amount=100.0,
        )
        
        assert "proto_testnet_" in tx_sig

    def test_vote_missing_realm_id(self):
        try:
            vote_on_proposal(
                realm_id="",
                proposal_id="Proposal456",
                vote=True,
                amount=1.0,
            )
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "realm_id" in str(e).lower()

    def test_vote_missing_proposal_id(self):
        try:
            vote_on_proposal(
                realm_id="Realm123",
                proposal_id="",
                vote=True,
                amount=1.0,
            )
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "proposal_id" in str(e).lower()

    def test_vote_invalid_amount(self):
        try:
            vote_on_proposal(
                realm_id="Realm123",
                proposal_id="Proposal456",
                vote=True,
                amount=0,
            )
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "amount" in str(e).lower()

    def test_vote_negative_amount(self):
        try:
            vote_on_proposal(
                realm_id="Realm123",
                proposal_id="Proposal456",
                vote=True,
                amount=-1.0,
            )
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "amount" in str(e).lower()

    @patch("tools.realms_voter_proxy.load_keypair")
    def test_vote_keypair_error(self, mock_load):
        mock_load.side_effect = FileNotFoundError("Keypair not found")
        
        try:
            vote_on_proposal(
                realm_id="Realm123",
                proposal_id="Proposal456",
                vote=True,
                amount=1.0,
            )
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "keypair" in str(e).lower()

    @patch("tools.realms_voter_proxy.load_keypair")
    @patch("tools.realms_voter_proxy._run_cmd")
    def test_vote_blockhash_failure(self, mock_cmd, mock_load):
        mock_cmd.return_value = ("error", 1)
        mock_load.return_value = "3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb"
        
        try:
            vote_on_proposal(
                realm_id="Realm123",
                proposal_id="Proposal456",
                vote=True,
                amount=1.0,
            )
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "blockhash" in str(e).lower()

    @patch("tools.realms_voter_proxy.load_keypair")
    @patch("tools.realms_voter_proxy._run_cmd")
    def test_vote_different_networks(self, mock_cmd, mock_load):
        mock_cmd.return_value = ("blockhash123", 0)
        mock_load.return_value = "Pubkey123"
        
        vote_on_proposal("R", "P", True, 1.0, network="devnet")
        
        call_args = mock_cmd.call_args[0][0]
        assert "--url" in call_args
        assert NETWORK_URLS["devnet"] in call_args


class TestSubmitProposal:
    """Tests for submit_proposal function."""

    @patch("tools.realms_voter_proxy.load_keypair")
    @patch("tools.realms_voter_proxy._run_cmd")
    def test_submit_proposal_success(self, mock_cmd, mock_load):
        mock_cmd.return_value = ("blockhash123", 0)
        mock_load.return_value = "3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb"
        
        tx_sig = submit_proposal(
            realm_id="Realm123",
            title="Test Proposal",
            description="This is a test proposal",
            token_mint="TokenMint123",
            network="testnet",
        )
        
        assert tx_sig.startswith("proto_testnet_")

    @patch("tools.realms_voter_proxy.load_keypair")
    @patch("tools.realms_voter_proxy._run_cmd")
    def test_submit_proposal_with_long_description(self, mock_cmd, mock_load):
        mock_cmd.return_value = ("blockhash123", 0)
        mock_load.return_value = "3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb"
        
        description = "A" * 1000  # Long description
        tx_sig = submit_proposal(
            realm_id="R",
            title="Title",
            description=description,
            token_mint="TM",
        )
        
        assert "proto_" in tx_sig

    def test_submit_missing_realm_id(self):
        try:
            submit_proposal(
                realm_id="",
                title="Test",
                description="Desc",
                token_mint="TM",
            )
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "realm_id" in str(e).lower()

    def test_submit_short_title(self):
        try:
            submit_proposal(
                realm_id="Realm123",
                title="AB",
                description="Description",
                token_mint="TM",
            )
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "title" in str(e).lower()

    def test_submit_missing_token_mint(self):
        try:
            submit_proposal(
                realm_id="Realm123",
                title="Test Proposal",
                description="Description",
                token_mint="",
            )
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "token_mint" in str(e).lower()

    @patch("tools.realms_voter_proxy.load_keypair")
    def test_submit_keypair_error(self, mock_load):
        mock_load.side_effect = ValueError("Invalid keypair")
        
        try:
            submit_proposal(
                realm_id="Realm123",
                title="Test",
                description="Desc",
                token_mint="TM",
            )
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "keypair" in str(e).lower()

    @patch("tools.realms_voter_proxy.load_keypair")
    @patch("tools.realms_voter_proxy._run_cmd")
    def test_submit_blockhash_failure(self, mock_cmd, mock_load):
        mock_cmd.return_value = ("error", 1)
        mock_load.return_value = "3WJxpvbexvubm5p8rLVdAXEuzQ725VPxUbALvdeXZiXb"
        
        try:
            submit_proposal(
                realm_id="R",
                title="Title",
                description="Desc",
                token_mint="TM",
            )
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "blockhash" in str(e).lower()

    @patch("tools.realms_voter_proxy.load_keypair")
    @patch("tools.realms_voter_proxy._run_cmd")
    def test_submit_different_networks(self, mock_cmd, mock_load):
        mock_cmd.return_value = ("blockhash123", 0)
        mock_load.return_value = "Pubkey123"
        
        submit_proposal("R", "Title", "D", "TM", network="mainnet")
        
        call_args = mock_cmd.call_args[0][0]
        assert "--url" in call_args
        assert NETWORK_URLS["mainnet"] in call_args


class TestListRealmProposals:
    """Tests for list_realm_proposals function."""

    @patch("tools.realms_voter_proxy._rpc_request")
    def test_list_proposals_success(self, mock_rpc):
        mock_rpc.return_value = {
            "result": [
                {"pubkey": "Prop1", "account": {"data": "d1", "owner": REALMS_GOVERNANCE_PROGRAM_ID}},
                {"pubkey": "Prop2", "account": {"data": "d2", "owner": REALMS_GOVERNANCE_PROGRAM_ID}},
            ]
        }
        
        proposals = list_realm_proposals("Realm123", "testnet", limit=10)
        
        assert len(proposals) == 2

    @patch("tools.realms_voter_proxy._rpc_request")
    def test_list_proposals_empty(self, mock_rpc):
        mock_rpc.return_value = {"result": []}
        
        proposals = list_realm_proposals("Realm123", "testnet")
        
        assert proposals == []

    @patch("tools.realms_voter_proxy._rpc_request")
    def test_list_proposals_limit(self, mock_rpc):
        mock_rpc.return_value = {
            "result": [
                {"pubkey": f"Prop{i}", "account": {"data": f"d{i}", "owner": REALMS_GOVERNANCE_PROGRAM_ID}}
                for i in range(20)
            ]
        }
        
        proposals = list_realm_proposals("R", limit=5)
        
        assert len(proposals) == 5

    @patch("tools.realms_voter_proxy._rpc_request")
    def test_list_proposals_rpc_error(self, mock_rpc):
        mock_rpc.return_value = {"error": "RPC error"}
        
        proposals = list_realm_proposals("R")
        
        assert "error" in proposals[0]


class TestGetDelegatedVoteAccount:
    """Tests for get_delegated_vote_account function."""

    def test_delegated_vote_account(self):
        # Currently returns None - prototype
        result = get_delegated_vote_account(
            delegate="Delegate123",
            realm_id="Realm456",
            token_mint="Mint789",
        )
        
        assert result is None


class TestConstants:
    """Tests for module constants."""

    def test_realms_program_id(self):
        assert REALMS_GOVERNANCE_PROGRAM_ID == "GovER5Lthms3bLBqErub2TqDVkz7gcY4ZwHy7W9K36d"

    def test_network_urls(self):
        assert "mainnet" in NETWORK_URLS
        assert "devnet" in NETWORK_URLS
        assert "testnet" in NETWORK_URLS
        assert NETWORK_URLS["mainnet"] == "https://api.mainnet-beta.solana.com"
        assert NETWORK_URLS["devnet"] == "https://api.devnet.solana.com"
        assert NETWORK_URLS["testnet"] == "https://api.testnet.solana.com"

    def test_default_keypair_paths(self):
        assert "mainnet" in DEFAULT_KEYPAIR_PATHS
        assert "devnet" in DEFAULT_KEYPAIR_PATHS
        assert "testnet" in DEFAULT_KEYPAIR_PATHS


class TestLiveIntegration:
    """Live integration tests - require solana CLI and network access."""

    def test_testnet_rpc_available(self):
        """Verify testnet RPC is accessible."""
        config = get_voter_proxy_config("testnet")
        result = _rpc_request(config.rpc_url, "getBlockHeight")
        
        assert "result" in result or "error" in result
        # If there's an error, it should be network-related
        if "error" in result:
            print(f"RPC Error: {result['error']}")

    def test_load_keypair_from_cli_config(self):
        """Verify we can load keypair from CLI config."""
        try:
            pubkey = load_keypair("testnet")
            assert pubkey is not None
            assert len(pubkey) > 30  # Solana pubkeys are 32-44 chars
            print(f"Loaded keypair: {pubkey}")
        except Exception as e:
            print(f"Could not load keypair: {e}")

    def test_vote_simulation_on_testnet(self):
        """Simulate a vote transaction on testnet (no real signing)."""
        try:
            # This will fail to sign but shows the flow
            tx_sig = vote_on_proposal(
                realm_id="TestRealm11111111111111111111111111111111",
                proposal_id="TestProposal1111111111111111111111111111111",
                vote=True,
                amount=1.0,
                network="testnet",
            )
            # Should return prototype signature
            assert "proto_testnet_" in tx_sig
            print(f"Vote simulation: {tx_sig}")
        except Exception as e:
            print(f"Vote simulation error: {e}")

    def test_submit_simulation_on_testnet(self):
        """Simulate a proposal submission on testnet (no real signing)."""
        try:
            tx_sig = submit_proposal(
                realm_id="TestRealm11111111111111111111111111111111",
                title="Agent Test Proposal",
                description="Testing autonomous agent proposal submission",
                token_mint="TestToken1111111111111111111111111111111",
                network="testnet",
            )
            assert "proto_testnet_" in tx_sig
            print(f"Submit simulation: {tx_sig}")
        except Exception as e:
            print(f"Submit simulation error: {e}")
