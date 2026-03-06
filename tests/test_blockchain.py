from unittest.mock import MagicMock, patch

import pytest

import src.services.blockchain_service as bs


@pytest.fixture
def mock_w3():
    with patch("src.services.blockchain_service.Web3") as MockWeb3:
        mock_instance = MagicMock()
        mock_instance.is_connected.return_value = True
        mock_instance.eth.chain_id = 80002
        mock_instance.eth.get_transaction_count.return_value = 1
        mock_instance.to_wei.return_value = 1000

        mock_contract = MagicMock()
        mock_contract.functions.mint.return_value.build_transaction.return_value = {
            "tx": "mock_mint"
        }
        mock_contract.functions.transfer.return_value.build_transaction.return_value = {
            "tx": "mock_transfer"
        }

        mock_instance.eth.contract.return_value = mock_contract

        mock_signed_tx = MagicMock()
        mock_signed_tx.raw_transaction = b"mock_raw_tx"
        mock_instance.eth.account.sign_transaction.return_value = mock_signed_tx

        mock_instance.eth.send_raw_transaction.return_value = b"mock_tx_hash"

        MockWeb3.return_value = mock_instance
        yield MockWeb3


@pytest.fixture
def mock_settings():
    with patch("src.services.blockchain_service.settings") as mock_settings:
        mock_settings.WEB3_RPC_URL = "http://mock-rpc"
        mock_settings.MASTER_WALLET_PRIVATE_KEY = "0x" + "0" * 64
        mock_settings.MASTERY_TOKEN_CONTRACT_ADDRESS = "0x" + "1" * 40
        mock_settings.EDUCOIN_TOKEN_CONTRACT_ADDRESS = "0x" + "2" * 40
        mock_settings.WEBHOOK_SECRET_KEY = "test_secret"
        yield mock_settings


@pytest.fixture
def mock_httpx_post():
    with patch("src.services.blockchain_service.httpx.post") as mock_post:
        yield mock_post


def test_mint_mastery_certificate_sync(mock_w3, mock_settings, mock_httpx_post):
    student_id = 123
    concept_id = "Advanced_Derivatives"

    tx_hash = bs.mint_mastery_token_sync(student_id, concept_id)

    # Check Web3 called correctly
    assert tx_hash == "6d6f636b5f74785f68617368"  # Built from b"mock_tx_hash".hex()

    # Should have called the mint function
    mock_instance = mock_w3.return_value
    mock_contract = mock_instance.eth.contract.return_value

    from eth_account import Account

    expected_address = Account.from_key(mock_settings.MASTER_WALLET_PRIVATE_KEY).address

    mock_contract.functions.mint.assert_called_with(
        expected_address, f"{student_id}:{concept_id}"
    )

    # Should fire off the webhook
    assert mock_httpx_post.call_count == 1
    call_args = mock_httpx_post.call_args[1]
    assert call_args["json"]["user_id"] == student_id
    assert call_args["json"]["skill_tag"] == concept_id
    assert call_args["json"]["transaction_hash"] == tx_hash


def test_transfer_credits_sync(mock_w3, mock_settings, mock_httpx_post):
    sender_id = 1
    receiver_id = 2
    amount = 5

    tx_hash = bs.transfer_credits_sync(sender_id, receiver_id, amount)

    assert tx_hash == "6d6f636b5f74785f68617368"

    mock_instance = mock_w3.return_value
    mock_contract = mock_instance.eth.contract.return_value

    # Called transfer function
    mock_contract.functions.transfer.assert_called()

    # Fired webhook
    assert mock_httpx_post.call_count == 1
    call_args = mock_httpx_post.call_args[1]
    assert call_args["json"]["sender_id"] == sender_id
    assert call_args["json"]["receiver_id"] == receiver_id
    assert call_args["json"]["amount"] == amount
    assert call_args["json"]["transaction_hash"] == tx_hash
