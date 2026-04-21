from functools import lru_cache
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    mt5_login: int | None = Field(default=None, alias="MT5_LOGIN")
    mt5_password: str | None = Field(default=None, alias="MT5_PASSWORD")
    mt5_server: str | None = Field(default=None, alias="MT5_SERVER")
    database_url: str = Field(default="postgresql+psycopg2://postgres:postgres@localhost:5432/trading_bot", alias="DATABASE_URL")
    symbol: str = Field(default="XAUUSD", alias="SYMBOL")
    uvicorn_host: str = Field(default="0.0.0.0", alias="UVICORN_HOST")
    uvicorn_port: int = Field(default=8000, alias="UVICORN_PORT")
    candle_limit: int = Field(default=500, alias="CANDLE_LIMIT")
    confidence_threshold: int = Field(default=75, alias="CONFIDENCE_THRESHOLD")

    @field_validator("mt5_login", mode="before")
    @classmethod
    def empty_login_to_none(cls, value):
        if value in ("", None):
            return None
        return int(value)

    @field_validator("mt5_password", "mt5_server", mode="before")
    @classmethod
    def empty_str_to_none(cls, value):
        if value == "":
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
