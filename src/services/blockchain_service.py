import asyncio
import hashlib
import hmac
import logging

import httpx
from eth_account import Account
from web3 import Web3

from src.core.config import settings

logger = logging.getLogger(__name__)

# Global httpx client for reuse
http_client = httpx.Client(timeout=10)

# Basic ABI for a mint function: function mint(address to, string memory skill)
MINIMAL_ERC721_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "string", "name": "skill", "type": "string"},
        ],
        "name": "mint",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]

# Basic ABI for a transfer function (mocking ERC20 transfer for simplicity)
MINIMAL_ERC20_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"},
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "payable": False,
        "stateMutability": "nonpayable",
        "type": "function",
    }
]


def generate_security_hash(user_id: int, skill_tag: str, tx_hash: str) -> str:
    """
    Generates an HMAC hash to secure the webhook payload.

    Inputs:
        - user_id (int): The ID of the user receiving the token.
        - skill_tag (str): The skill tag associated with the mastery.
        - tx_hash (str): The blockchain transaction hash.
    Output:
        - str: The generated HMAC SHA-256 hash.
    EduMate Module: Security Anchor / SocraticBridge
    """
    message = f"{user_id}:{skill_tag}:{tx_hash}".encode("utf-8")
    secret = settings.WEBHOOK_SECRET_KEY.encode("utf-8")
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def generate_credit_transfer_security_hash(
    sender_id: int, receiver_id: int, amount: int, tx_hash: str
) -> str:
    """
    Generates an HMAC hash to secure the credit transfer webhook payload.

    Inputs:
        - sender_id (int): The ID of the student sending credits.
        - receiver_id (int): The ID of the tutor receiving credits.
        - amount (int): The number of credits transferred.
        - tx_hash (str): The blockchain transaction hash.
    Output:
        - str: The generated HMAC SHA-256 hash.
    EduMate Module: Security Anchor / SkillSwarm
    """
    message = f"{sender_id}:{receiver_id}:{amount}:{tx_hash}".encode("utf-8")
    secret = settings.WEBHOOK_SECRET_KEY.encode("utf-8")
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def mint_mastery_token_sync(user_id: int, skill_tag: str) -> str | None:
    """
    Synchronous Web3 logic to mint a mastery token.
    Intended to be run in an async executor thread to prevent blocking.

    Inputs:
        - user_id (int): Target user ID.
        - skill_tag (str): Target concept for the NFT.
    Output:
        - str | None: The transaction hash if successful, None otherwise.
    EduMate Module: Security Anchor
    """
    if not settings.WEB3_RPC_URL or not settings.MASTER_WALLET_PRIVATE_KEY:
        logger.warning("Web3 configuration missing. Skipping Mastery Token minting.")
        return None

    try:
        w3 = Web3(Web3.HTTPProvider(settings.WEB3_RPC_URL))
        if not w3.is_connected():
            logger.error("Failed to connect to Web3 Provider.")
            return None

        account = Account.from_key(settings.MASTER_WALLET_PRIVATE_KEY)
        contract = w3.eth.contract(
            address=settings.MASTERY_TOKEN_CONTRACT_ADDRESS, abi=MINIMAL_ERC721_ABI
        )

        # For this MVP, we mint to the platform relayer wallet rather than individual user wallets,
        # but encode their internal ID + skill into the transaction or a centralized map.
        target_wallet = account.address

        nonce = w3.eth.get_transaction_count(account.address)

        # Build the transaction
        tx = contract.functions.mint(
            target_wallet, f"{user_id}:{skill_tag}"
        ).build_transaction(
            {
                "chainId": w3.eth.chain_id,
                "gas": 2000000,
                "maxFeePerGas": w3.to_wei("2", "gwei"),
                "maxPriorityFeePerGas": w3.to_wei("1", "gwei"),
                "nonce": nonce,
            }
        )

        signed_tx = w3.eth.account.sign_transaction(
            tx, private_key=settings.MASTER_WALLET_PRIVATE_KEY
        )
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

        hex_hash = tx_hash.hex()
        logger.info(
            f"Successfully minted Mastery Token for User {user_id} - Hash: {hex_hash}"
        )

        # Trigger internal webhook to log this in PostgreSQL securely
        sec_hash = generate_security_hash(user_id, skill_tag, hex_hash)
        payload = {
            "user_id": user_id,
            "skill_tag": skill_tag,
            "transaction_hash": hex_hash,
            "security_hash": sec_hash,
        }

        # We fire and forget the webhook call
        try:
            http_client.post(
                "http://127.0.0.1:8000/api/v1/webhooks/blockchain/mastery_token",
                json=payload,
            )
        except Exception as e:
            logger.error(f"Failed to trigger Mastery Token webhook: {e}")

        return hex_hash

    except Exception as e:
        logger.error(f"Error minting mastery token: {e}")
        return None


async def mint_mastery_certificate(user_id: int, concept_id: str) -> None:
    """
    Async wrapper to prevent Web3 synchronous HTTP requests from blocking the event loop.
    Re-aliased to match SocraticBridge naming.

    Inputs:
        - user_id (int): Target user ID.
        - concept_id (str): Target concept for the NFT.
    Output:
        - None
    EduMate Module: Security Anchor / SocraticBridge
    """
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, mint_mastery_token_sync, user_id, concept_id)


# Preserving old alias dynamically just in case
mint_mastery_token = mint_mastery_certificate


def mint_verified_peer_mentor_badge_sync(user_id: int) -> str | None:
    """
    Synchronous Web3 logic to mint a 'Verified Peer Mentor' badge.
    Triggered after 5 'Excellent' feedback ratings.
    """
    if not settings.WEB3_RPC_URL or not settings.MASTER_WALLET_PRIVATE_KEY:
        logger.warning(
            "Web3 configuration missing. Skipping Peer Mentor Badge minting."
        )
        return None

    try:
        w3 = Web3(Web3.HTTPProvider(settings.WEB3_RPC_URL))
        if not w3.is_connected():
            return None

        account = Account.from_key(settings.MASTER_WALLET_PRIVATE_KEY)
        contract = w3.eth.contract(
            address=settings.MASTERY_TOKEN_CONTRACT_ADDRESS, abi=MINIMAL_ERC721_ABI
        )

        target_wallet = account.address
        nonce = w3.eth.get_transaction_count(account.address)

        # 'VerifiedPeerMentor' is passed as the skill string for the generic ERC721 mint
        tx = contract.functions.mint(
            target_wallet, f"{user_id}:VerifiedPeerMentor"
        ).build_transaction(
            {
                "chainId": w3.eth.chain_id,
                "gas": 2000000,
                "maxFeePerGas": w3.to_wei("2", "gwei"),
                "maxPriorityFeePerGas": w3.to_wei("1", "gwei"),
                "nonce": nonce,
            }
        )

        signed_tx = w3.eth.account.sign_transaction(
            tx, private_key=settings.MASTER_WALLET_PRIVATE_KEY
        )
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

        hex_hash = tx_hash.hex()
        logger.info(
            f"Successfully minted Verified Peer Mentor Badge for User {user_id} - Hash: {hex_hash}"
        )

        return hex_hash

    except Exception as e:
        logger.error(f"Error minting peer mentor badge: {e}")
        return None


async def mint_verified_peer_mentor_badge(user_id: int) -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, mint_verified_peer_mentor_badge_sync, user_id)


def transfer_credits_sync(sender_id: int, receiver_id: int, amount: int) -> str | None:
    """
    Synchronous Web3 logic to transfer EduCoins.

    Inputs:
        - sender_id (int): Sending user ID (Student).
        - receiver_id (int): Receiving user ID (Tutor).
        - amount (int): Amount of tokens to transfer.
    Output:
        - str | None: The transaction hash if successful, None otherwise.
    EduMate Module: Security Anchor
    """
    if not settings.WEB3_RPC_URL or not settings.MASTER_WALLET_PRIVATE_KEY:
        logger.warning(
            "Web3 configuration missing. Skipping Credit Transfer on-chain logging."
        )
        return None

    try:
        w3 = Web3(Web3.HTTPProvider(settings.WEB3_RPC_URL))
        if not w3.is_connected():
            return None

        account = Account.from_key(settings.MASTER_WALLET_PRIVATE_KEY)

        # NOTE: Mocking specific sender/receiver wallets logic by centralizing transfer
        # calls through the master wallet for the sake of the hackathon prototype.
        # In prod, this would use a mapping of user_id -> wallet address.
        target_wallet = account.address

        # We mock the contract address if not strictly provided
        token_address = getattr(
            settings,
            "EDUCOIN_TOKEN_CONTRACT_ADDRESS",
            settings.MASTERY_TOKEN_CONTRACT_ADDRESS,
        )
        contract = w3.eth.contract(address=token_address, abi=MINIMAL_ERC20_ABI)

        nonce = w3.eth.get_transaction_count(account.address)

        # Simplified mock transfer to the platform treasury
        tx = contract.functions.transfer(
            target_wallet, w3.to_wei(amount, "ether")
        ).build_transaction(
            {
                "chainId": w3.eth.chain_id,
                "gas": 100000,
                "maxFeePerGas": w3.to_wei("2", "gwei"),
                "maxPriorityFeePerGas": w3.to_wei("1", "gwei"),
                "nonce": nonce,
            }
        )

        signed_tx = w3.eth.account.sign_transaction(
            tx, private_key=settings.MASTER_WALLET_PRIVATE_KEY
        )
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

        hex_hash = tx_hash.hex()
        logger.info(
            f"Successfully transferred credits: {sender_id} -> {receiver_id} - Hash: {hex_hash}"
        )

        sec_hash = generate_credit_transfer_security_hash(
            sender_id, receiver_id, amount, hex_hash
        )
        payload = {
            "sender_id": sender_id,
            "receiver_id": receiver_id,
            "amount": amount,
            "transaction_hash": hex_hash,
            "security_hash": sec_hash,
        }

        try:
            http_client.post(
                "http://127.0.0.1:8000/api/v1/webhooks/blockchain/credit_transfer",
                json=payload,
            )
        except Exception as e:
            logger.error(f"Failed to trigger Credit Transfer webhook: {e}")

        return hex_hash

    except Exception as e:
        logger.error(f"Error transferring credits: {e}")
        return None


async def transfer_credits(sender_id: int, receiver_id: int, amount: int) -> None:
    """
    Async wrapper for credit transfers.

    Inputs:
        - sender_id (int): Sending user ID (Student).
        - receiver_id (int): Receiving user ID (Tutor).
        - amount (int): Amount of tokens to transfer.
    Output:
        - None
    EduMate Module: Security Anchor / SkillSwarm
    """
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None, transfer_credits_sync, sender_id, receiver_id, amount
    )
