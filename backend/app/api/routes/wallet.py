from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import get_session
from app.schemas.wallet import WalletConfigureRequest, WalletResponse, WalletTestDeriveResponse, WalletTestResponse
from app.services.wallet_credentials import (
    ApiCredentialDeriver,
    PolymarketSdkCredentialDeriver,
    configure_wallet,
    delete_wallet_credentials,
    derive_api_credentials,
    get_wallet_status,
    test_derive_api_credentials,
    test_wallet_credentials,
    wallet_response,
)

router = APIRouter()


def get_api_credential_deriver() -> ApiCredentialDeriver:
    return PolymarketSdkCredentialDeriver()


@router.get("/wallet", response_model=WalletResponse)
async def wallet_status(session: AsyncSession = Depends(get_session)) -> WalletResponse:
    try:
        return await get_wallet_status(session)
    except OperationalError as exc:
        _raise_wallet_table_missing_if_needed(exc)
        raise


@router.post("/wallet/configure", response_model=WalletResponse)
async def configure_wallet_route(
    request: WalletConfigureRequest,
    session: AsyncSession = Depends(get_session),
    deriver: ApiCredentialDeriver = Depends(get_api_credential_deriver),
) -> WalletResponse:
    try:
        credential = await configure_wallet(request, session, deriver=deriver)
        return wallet_response(credential)
    except OperationalError as exc:
        _raise_wallet_table_missing_if_needed(exc)
        raise


@router.post("/wallet/derive-api-credentials", response_model=WalletResponse)
async def derive_wallet_api_credentials_route(
    session: AsyncSession = Depends(get_session),
    deriver: ApiCredentialDeriver = Depends(get_api_credential_deriver),
) -> WalletResponse:
    try:
        credential = await derive_api_credentials(session, deriver=deriver)
        return wallet_response(credential)
    except OperationalError as exc:
        _raise_wallet_table_missing_if_needed(exc)
        raise


@router.post("/wallet/test", response_model=WalletTestResponse)
async def test_wallet_credentials_route(session: AsyncSession = Depends(get_session)) -> WalletTestResponse:
    try:
        return await test_wallet_credentials(session)
    except OperationalError as exc:
        _raise_wallet_table_missing_if_needed(exc)
        raise


@router.post("/wallet/test-derive", response_model=WalletTestDeriveResponse)
async def test_derive_wallet_api_credentials_route(
    request: WalletConfigureRequest,
    deriver: ApiCredentialDeriver = Depends(get_api_credential_deriver),
) -> WalletTestDeriveResponse:
    if get_settings().app_env.lower() != "development":
        raise AppError("HTTP_ERROR", technical_detail="Wallet derivation test endpoint is development-only", status_code=404)
    return await test_derive_api_credentials(request, deriver=deriver)


@router.delete("/wallet", response_model=WalletResponse)
async def delete_wallet_route(session: AsyncSession = Depends(get_session)) -> WalletResponse:
    try:
        await delete_wallet_credentials(session)
        return WalletResponse(configured=False, api_key_configured=False)
    except OperationalError as exc:
        _raise_wallet_table_missing_if_needed(exc)
        raise


def _raise_wallet_table_missing_if_needed(exc: OperationalError) -> None:
    detail = str(exc.orig if getattr(exc, "orig", None) is not None else exc)
    if "wallet_credentials" in detail and ("no such table" in detail.lower() or "does not exist" in detail.lower()):
        raise AppError("WALLET_TABLE_MISSING", technical_detail=detail, status_code=503) from exc
