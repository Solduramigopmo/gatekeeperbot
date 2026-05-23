from __future__ import annotations

import json
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, Field, HttpUrl, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Plan(BaseModel):
    id: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=64)
    days: int = Field(gt=0, le=3650)
    price: Decimal = Field(gt=Decimal("0"))

    @field_validator("price", mode="before")
    @classmethod
    def _coerce_price(cls, value: object) -> object:
        if isinstance(value, (int, float, str)):
            return Decimal(str(value))
        return value


def _csv_ints(value: str | list[int]) -> list[int]:
    if isinstance(value, list):
        return value
    return [int(x.strip()) for x in value.split(",") if x.strip()]


def _csv_strs(value: str | list[str]) -> list[str]:
    if isinstance(value, list):
        return value
    return [x.strip().upper() for x in value.split(",") if x.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    bot_token: str = Field(min_length=10)
    channel_id: int
    channel_username: str | None = None
    admin_ids: Annotated[list[int], NoDecode, Field(default_factory=list)]

    crypto_pay_token: str = Field(min_length=10)
    crypto_pay_base_url: HttpUrl = Field(default="https://pay.crypt.bot") 
    crypto_pay_assets: Annotated[
        list[str], NoDecode, Field(default_factory=lambda: ["USDT", "TON"])
    ]

    webhook_enabled: bool = False
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8080
    webhook_path: str = "/cryptopay"
    poll_interval_seconds: int = Field(default=60, ge=15, le=3600)

    subscription_plans: list[Plan]
    reminder_days: Annotated[
        list[int], NoDecode, Field(default_factory=lambda: [3, 1])
    ]

    welcome_image: Path | None = None
    support_url: str | None = None
    info_url: str | None = None

    database_url: str = "sqlite+aiosqlite:///data/bot.sqlite3"

    log_level: str = "INFO"
    throttle_buy_per_minute: int = Field(default=5, ge=1, le=120)

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _parse_admins(cls, value: object) -> object:
        if isinstance(value, str):
            return _csv_ints(value)
        return value

    @field_validator("crypto_pay_assets", mode="before")
    @classmethod
    def _parse_assets(cls, value: object) -> object:
        if isinstance(value, str):
            return _csv_strs(value)
        return value

    @field_validator("reminder_days", mode="before")
    @classmethod
    def _parse_reminders(cls, value: object) -> object:
        if isinstance(value, str):
            return sorted({int(x) for x in _csv_ints(value)}, reverse=True)
        if isinstance(value, list):
            return sorted({int(x) for x in value}, reverse=True)
        return value

    @field_validator("subscription_plans", mode="before")
    @classmethod
    def _parse_plans(cls, value: object) -> object:
        if isinstance(value, str):
            parsed = json.loads(value)
            if not isinstance(parsed, list):
                raise ValueError("SUBSCRIPTION_PLANS must decode to a JSON array")
            return parsed
        return value

    @field_validator("subscription_plans")
    @classmethod
    def _unique_plan_ids(cls, value: list[Plan]) -> list[Plan]:
        if not value:
            raise ValueError("at least one subscription plan is required")
        seen: set[str] = set()
        for plan in value:
            if plan.id in seen:
                raise ValueError(f"duplicate plan id: {plan.id}")
            seen.add(plan.id)
        return value

    @field_validator("welcome_image", mode="before")
    @classmethod
    def _empty_path_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    def plan_by_id(self, plan_id: str) -> Plan | None:
        return next((p for p in self.subscription_plans if p.id == plan_id), None)

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    return Settings()  
