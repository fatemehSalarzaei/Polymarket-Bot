from app.schemas.websocket import BotStatus
from app.services.dashboard_broadcaster import DashboardBroadcaster, dashboard_broadcaster


class BotStateService:
    def __init__(self, broadcaster: DashboardBroadcaster = dashboard_broadcaster) -> None:
        self._broadcaster = broadcaster
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def status(self) -> BotStatus:
        return BotStatus(
            running=self._running,
            market_ws_fresh=self._broadcaster.freshness.is_fresh("market_ws", max_age_seconds=10),
            rtds_fresh=self._broadcaster.freshness.is_fresh("rtds_btc", max_age_seconds=10),
            message="Run celery_worker, celery_beat, and realtime_runner for background execution.",
        )

    async def start(self) -> BotStatus:
        self._running = True
        status = self.status()
        await self._broadcaster.broadcast("bot_status", status)
        return status

    async def stop(self) -> BotStatus:
        self._running = False
        status = self.status()
        await self._broadcaster.broadcast("bot_status", status)
        return status


bot_state_service = BotStateService()
