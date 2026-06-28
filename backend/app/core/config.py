from functools import lru_cache

from pydantic import AnyHttpUrl, Field, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+asyncpg://polymarket:polymarket@postgres:5432/polymarket_bot"
    redis_url: RedisDsn = "redis://redis:6379/0"
    credential_encryption_key: str = ""

    polymarket_clob_host: AnyHttpUrl = "https://clob.polymarket.com"
    polymarket_gamma_host: AnyHttpUrl = "https://gamma-api.polymarket.com"
    polymarket_market_wss: str = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    polymarket_rtds_wss: str = "wss://ws-live-data.polymarket.com"
    polymarket_http_connect_timeout: float = 3.0
    polymarket_http_read_timeout: float = 20.0
    polymarket_http_write_timeout: float = 5.0
    polymarket_http_pool_timeout: float = 5.0
    polymarket_http_max_retries: int = 3
    polymarket_http_retry_base_delay_seconds: float = 0.5
    chainlink_start_tick_tolerance_seconds: int = 30
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
    redeem_enabled: bool = False
    redeem_dry_run: bool = True
    paper_trading_enabled: bool = True
    kill_switch_active: bool = False
    final_window_seconds: int = 180
    min_edge: float = 0.05
    max_spread: float = 0.03
    max_slippage: float = 0.02
    max_order_size_usd: float = 1
    max_daily_loss_usd: float = 1
    max_data_age_seconds: int = 10
    default_order_type: str = Field(default="FAK", pattern="^(GTC|FOK|GTD|FAK)$")
    pusd_contract_address: str = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"
    ctf_parent_collection_id: str = "0x0000000000000000000000000000000000000000000000000000000000000000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
