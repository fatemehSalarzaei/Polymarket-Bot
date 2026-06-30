from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol
import asyncio

from app.core.config import Settings, get_settings
from app.services.wallet_credentials import TradingCredentialBundle, get_active_wallet_credentials_for_trading


@dataclass
class RedeemAdapterResult:
    submitted: bool
    confirmed: bool = False
    dry_run: bool = False
    tx_hash: str | None = None
    amount_redeemed: Decimal | None = None
    raw_response: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None


class PolymarketRedeemAdapter(Protocol):
    credentials_configured: bool
    wallet_address: str | None
    wallet_credential_id: int | None
    redeem_flow_supported: bool
    redeem_flow_blocking_reason: str | None

    async def redeem(self, condition_id: str, index_sets: list[int]) -> RedeemAdapterResult: ...

    async def get_pusd_balance(self, wallet_address: str) -> Decimal | None: ...


class SafeDryRunRedeemAdapter:
    credentials_configured = True
    redeem_flow_supported = True
    redeem_flow_blocking_reason = None

    def __init__(self, *, wallet_address: str | None = None, wallet_credential_id: int | None = None) -> None:
        self.wallet_address = wallet_address
        self.wallet_credential_id = wallet_credential_id

    async def redeem(self, condition_id: str, index_sets: list[int]) -> RedeemAdapterResult:
        return RedeemAdapterResult(
            submitted=False,
            confirmed=False,
            dry_run=True,
            raw_response={
                "dry_run": True,
                "condition_id": condition_id,
                "index_sets": index_sets,
                "message": "Redeem dry-run active; no blockchain transaction submitted.",
            },
            error_message="REDEEM_DRY_RUN",
        )

    async def get_pusd_balance(self, wallet_address: str) -> Decimal | None:
        return None


class BackendOnlyPolymarketRedeemAdapter:
    def __init__(self, settings: Settings | None = None, *, bundle: TradingCredentialBundle | None = None) -> None:
        self._settings = settings or get_settings()
        self._bundle = bundle
        self.wallet_address = bundle.wallet_address if bundle is not None else self._settings.polymarket_funder_address or None
        self.wallet_credential_id = bundle.wallet_credential_id if bundle is not None else None
        self.credentials_configured = bundle is not None or bool(
            self._settings.private_key
            and self._settings.polymarket_api_key
            and self._settings.polymarket_api_secret
            and self._settings.polymarket_api_passphrase
            and self._settings.polymarket_funder_address
        )
        self.redeem_flow_blocking_reason = _redeem_flow_blocking_reason(settings=self._settings, bundle=bundle)
        self.redeem_flow_supported = self.redeem_flow_blocking_reason is None

    async def redeem(self, condition_id: str, index_sets: list[int]) -> RedeemAdapterResult:
        return await asyncio.to_thread(self._redeem_sync, condition_id, index_sets)

    async def get_pusd_balance(self, wallet_address: str) -> Decimal | None:
        return await asyncio.to_thread(self._get_erc20_balance_sync, wallet_address)

    def _redeem_sync(self, condition_id: str, index_sets: list[int]) -> RedeemAdapterResult:
        if not self._settings.polygon_rpc_url:
            return RedeemAdapterResult(
                submitted=False,
                raw_response={},
                error_message="POLYGON_RPC_URL_MISSING",
            )
        if not self._settings.resolved_collateral_token_address:
            return RedeemAdapterResult(
                submitted=False,
                raw_response={},
                error_message="COLLATERAL_TOKEN_MISSING",
            )
        if not self._settings.conditional_tokens_contract_address:
            return RedeemAdapterResult(
                submitted=False,
                raw_response={},
                error_message="CONDITIONAL_TOKENS_CONTRACT_MISSING",
            )
        if self._bundle is None:
            return RedeemAdapterResult(
                submitted=False,
                raw_response={},
                error_message="WALLET_CONFIG_MISSING",
            )
        try:
            from eth_account import Account
            from web3 import Web3
        except ImportError as exc:
            return RedeemAdapterResult(
                submitted=False,
                raw_response={},
                error_message=f"WEB3_IMPORT_FAILED:{type(exc).__name__}",
            )

        account = Account.from_key(self._bundle.private_key)
        from_address = Web3.to_checksum_address(account.address)
        funder_address = self._bundle.funder_address
        if self.redeem_flow_blocking_reason is not None:
            return RedeemAdapterResult(
                submitted=False,
                raw_response={"wallet_address": from_address, "funder_address": funder_address},
                error_message=self.redeem_flow_blocking_reason,
            )

        web3 = Web3(Web3.HTTPProvider(self._settings.polygon_rpc_url))
        ctf = web3.eth.contract(
            address=Web3.to_checksum_address(self._settings.conditional_tokens_contract_address),
            abi=_CONDITIONAL_TOKENS_ABI,
        )
        collateral = Web3.to_checksum_address(self._settings.resolved_collateral_token_address)
        tx = ctf.functions.redeemPositions(
            collateral,
            bytes.fromhex(self._settings.ctf_parent_collection_id.removeprefix("0x")),
            bytes.fromhex(condition_id.removeprefix("0x")),
            index_sets,
        ).build_transaction(
            {
                "from": from_address,
                "chainId": self._bundle.chain_id,
                "nonce": web3.eth.get_transaction_count(from_address),
                "gasPrice": web3.eth.gas_price,
            }
        )
        tx.setdefault("gas", web3.eth.estimate_gas(tx))
        signed = account.sign_transaction(tx)
        tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
        confirmed = int(receipt.get("status", 0)) == 1
        return RedeemAdapterResult(
            submitted=True,
            confirmed=confirmed,
            tx_hash=web3.to_hex(tx_hash),
            raw_response={
                "transaction_hash": web3.to_hex(tx_hash),
                "block_number": receipt.get("blockNumber"),
                "status": receipt.get("status"),
                "condition_id": condition_id,
                "index_sets": index_sets,
                "ctf_contract_address": self._settings.conditional_tokens_contract_address,
                "collateral_token_address": self._settings.resolved_collateral_token_address,
            },
            error_message=None if confirmed else "REDEEM_TX_REVERTED",
        )

    def _get_erc20_balance_sync(self, wallet_address: str) -> Decimal | None:
        if not self._settings.polygon_rpc_url:
            return None
        if not self._settings.resolved_collateral_token_address:
            return None
        try:
            from web3 import Web3
        except ImportError:
            return None
        web3 = Web3(Web3.HTTPProvider(self._settings.polygon_rpc_url))
        token = web3.eth.contract(
            address=Web3.to_checksum_address(self._settings.resolved_collateral_token_address),
            abi=_ERC20_ABI,
        )
        raw_balance = token.functions.balanceOf(Web3.to_checksum_address(wallet_address)).call()
        try:
            decimals = token.functions.decimals().call()
        except Exception:
            decimals = 6
        return Decimal(raw_balance) / (Decimal(10) ** Decimal(decimals))


_CONDITIONAL_TOKENS_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "collateralToken", "type": "address"},
            {"name": "parentCollectionId", "type": "bytes32"},
            {"name": "conditionId", "type": "bytes32"},
            {"name": "indexSets", "type": "uint256[]"},
        ],
        "name": "redeemPositions",
        "outputs": [],
        "payable": False,
        "stateMutability": "nonpayable",
        "type": "function",
    }
]

_ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
]


def build_redeem_adapter(settings: Settings | None = None) -> PolymarketRedeemAdapter:
    config = settings or get_settings()
    if config.redeem_dry_run or config.real_order_dry_run:
        return SafeDryRunRedeemAdapter(wallet_address=config.polymarket_funder_address or None)
    return BackendOnlyPolymarketRedeemAdapter(config)


async def build_redeem_adapter_from_stored_wallet(session, *, user_id: int | None, settings: Settings | None = None) -> PolymarketRedeemAdapter:
    config = settings or get_settings()
    bundle = await get_active_wallet_credentials_for_trading(session, user_id=user_id)
    if config.redeem_dry_run or config.real_order_dry_run:
        return SafeDryRunRedeemAdapter(
            wallet_address=bundle.wallet_address,
            wallet_credential_id=bundle.wallet_credential_id,
        )
    return BackendOnlyPolymarketRedeemAdapter(config, bundle=bundle)


def _redeem_flow_blocking_reason(*, settings: Settings, bundle: TradingCredentialBundle | None) -> str | None:
    if not settings.polygon_rpc_url:
        return "POLYGON_RPC_URL_MISSING"
    if not settings.resolved_collateral_token_address:
        return "COLLATERAL_TOKEN_MISSING"
    if not settings.conditional_tokens_contract_address:
        return "CONDITIONAL_TOKENS_CONTRACT_MISSING"
    if bundle is not None and bundle.funder_address and bundle.funder_address.lower() != bundle.wallet_address.lower():
        return "PROXY_WALLET_REDEEM_REQUIRES_RELAYER"
    return None
