from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.audit import AuditLog
from app.schemas.execution import GeoblockStatus
from app.schemas.websocket import BotStatus
from app.services.bot_state import bot_state_service
from app.services.geoblock import GeoblockClient
from app.services.settings import get_or_create_strategy_settings, serialize_strategy_settings

router = APIRouter()


def get_geoblock_client() -> GeoblockClient:
    return GeoblockClient()


@router.get("/bot/status", response_model=BotStatus)
async def get_bot_status() -> BotStatus:
    return bot_state_service.status()


@router.post("/bot/start", response_model=BotStatus)
async def start_bot() -> BotStatus:
    return await bot_state_service.start()


@router.post("/bot/stop", response_model=BotStatus)
async def stop_bot() -> BotStatus:
    return await bot_state_service.stop()


@router.get("/bot/geoblock-status", response_model=GeoblockStatus)
async def get_geoblock_status(
    geoblock_client: GeoblockClient = Depends(get_geoblock_client),
) -> GeoblockStatus:
    return await geoblock_client.get_status()


@router.post("/bot/kill-switch")
async def activate_kill_switch(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    settings = await get_or_create_strategy_settings(session)
    before = serialize_strategy_settings(settings)
    settings.kill_switch_active = True
    settings.trading_enabled = False
    session.add(settings)
    await session.flush()
    await session.refresh(settings)
    session.add(
        AuditLog(
            actor="dashboard",
            action="bot.kill_switch",
            entity_type="strategy_settings",
            entity_id=str(settings.id),
            before=before,
            after=serialize_strategy_settings(settings),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    await session.commit()
    return {"kill_switch_active": True, "trading_enabled": False}
