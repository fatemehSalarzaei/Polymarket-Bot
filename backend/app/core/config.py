from functools import lru_cache

from pydantic import AnyHttpUrl, Field, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+asyncpg://polymarket:polymarket@postgres:5432/polymarket_bot"
    redis_url: RedisDsn = "redis://redis:6379/0"

    polymarket_clob_host: AnyHttpUrl = "https://clob.polymarket.com"
    polymarket_gamma_host: AnyHttpUrl = "https://gamma-api.polymarket.com"
    polymarket_rtds_wss: str = "wss://ws-live-data.polymarket.com"
    polymarket_user_wss: str = "wss://clob.polymarket.com/ws/user"
    polymarket_chain_id: int = 137

    private_key: str = ""
    polymarket_api_key: str = ""
    polymarket_api_secret: str = ""
    polymarket_api_passphrase: str = ""
    polymarket_funder_address: str = ""
    polymarket_signature_type: int = 3

    trading_enabled: bool = False
    real_order_dry_run: bool = True
    paper_trading_enabled: bool = True
    kill_switch_active: bool = False
    final_window_seconds: int = 180
    min_edge: float = 0.04
    max_spread: float = 0.02
    max_slippage: float = 0.02
    max_order_size_usd: float = 10
    max_daily_loss_usd: float = 50
    max_data_age_seconds: int = 5
    default_order_type: str = Field(default="FAK", pattern="^(GTC|FOK|GTD|FAK)$")


@lru_cache
def get_settings() -> Settings:
    return Settings()
