from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.audit import AuditLog
from app.schemas.execution import GeoblockStatus
from app.schemas.websocket import BotStatus
from app.services.bot_state import bot_state_service
from app.services.geoblock import GeoblockClient
from app.services.settings import get_or_create_strategy_settings, serialize_strategy_settings
from app.services.auth import get_current_user
from app.models.user import User

router = APIRouter()


def get_geoblock_client() -> GeoblockClient:
    return GeoblockClient()


@router.get("/bot/status", response_model=BotStatus)
async def get_bot_status() -> BotStatus:
    return bot_state_service.status()


@router.post("/bot/start", response_model=BotStatus)
async def start_bot(
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User | None = Depends(get_current_user),
) -> BotStatus:
    status = await bot_state_service.start()
    session.add(
        AuditLog(
            actor="dashboard",
            action="bot.start",
            entity_type="bot",
            entity_id="runtime",
            before={"running": False},
            after=status.model_dump(mode="json"),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    await session.commit()
    return status


@router.post("/bot/stop", response_model=BotStatus)
async def stop_bot(
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User | None = Depends(get_current_user),
) -> BotStatus:
    status = await bot_state_service.stop()
    session.add(
        AuditLog(
            actor="dashboard",
            action="bot.stop",
            entity_type="bot",
            entity_id="runtime",
            before={"running": True},
            after=status.model_dump(mode="json"),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    await session.commit()
    return status


@router.get("/bot/geoblock-status", response_model=GeoblockStatus)
async def get_geoblock_status(
    geoblock_client: GeoblockClient = Depends(get_geoblock_client),
) -> GeoblockStatus:
    return await geoblock_client.get_status()


@router.post("/bot/kill-switch")
async def activate_kill_switch(
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User | None = Depends(get_current_user),
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
