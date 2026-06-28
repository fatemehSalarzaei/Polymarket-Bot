from celery import Celery

from app.core.config import get_settings


settings = get_settings()

celery_app = Celery(
    "polymarket_bot",
    broker=str(settings.redis_url),
    backend=str(settings.redis_url),
    include=[
        "app.tasks.market_tasks",
        "app.tasks.strategy_tasks",
        "app.tasks.settlement_tasks",
        "app.tasks.redeem_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    beat_schedule={
        "discover-current-market": {
            "task": "app.tasks.market.discover_current_market",
            "schedule": 5.0,
        },
        "fetch-current-orderbook": {
            "task": "app.tasks.market.fetch_current_orderbook",
            "schedule": 15.0,
        },
        "evaluate-current-strategy": {
            "task": "app.tasks.strategy.evaluate_current",
            "schedule": 5.0,
        },
        "settle-finished-markets": {
            "task": "app.tasks.settlement.settle_finished_markets",
            "schedule": 15.0,
        },
        "redeem-resolved-winning-positions": {
            "task": "app.tasks.redeem.redeem_resolved_winning_positions",
            "schedule": 15.0,
        },
    },
)
