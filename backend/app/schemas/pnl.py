from decimal import Decimal

from pydantic import BaseModel


class PnlSummaryResponse(BaseModel):
    paper_pnl: Decimal
    real_pnl: Decimal
    paper_orders: int
    real_orders: int
    settled_markets: int
    winning_trades: int
    losing_trades: int
    win_rate: Decimal
    no_trade_count: int

