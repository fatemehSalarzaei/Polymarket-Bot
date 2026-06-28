from __future__ import annotations

from fastapi import APIRouter, Depends
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
    return await get_wallet_status(session)


@router.post("/wallet/configure", response_model=WalletResponse)
async def configure_wallet_route(
    request: WalletConfigureRequest,
    session: AsyncSession = Depends(get_session),
    deriver: ApiCredentialDeriver = Depends(get_api_credential_deriver),
) -> WalletResponse:
    credential = await configure_wallet(request, session, deriver=deriver)
    return wallet_response(credential)


@router.post("/wallet/derive-api-credentials", response_model=WalletResponse)
async def derive_wallet_api_credentials_route(
    session: AsyncSession = Depends(get_session),
    deriver: ApiCredentialDeriver = Depends(get_api_credential_deriver),
) -> WalletResponse:
    credential = await derive_api_credentials(session, deriver=deriver)
    return wallet_response(credential)


@router.post("/wallet/test", response_model=WalletTestResponse)
async def test_wallet_credentials_route(session: AsyncSession = Depends(get_session)) -> WalletTestResponse:
    return await test_wallet_credentials(session)


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
    await delete_wallet_credentials(session)
    return WalletResponse(configured=False, api_key_configured=False)
