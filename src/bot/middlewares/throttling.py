from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

from .. import texts
from ..config import Settings
from ..keyboards.callbacks import BuyAsset, BuyPlan, Invoice, Menu


class Clock(Protocol):
    def __call__(self) -> float: ...


class ThrottlingMiddleware(BaseMiddleware):
"""Тариф - ограничивает дорогостоящие действия (поток покупок, проверки платежей).

 Такие дешевые действия, как открытие главного меню, не регулируются. Администраторы
не имеют права изменять настройки — они должны иметь возможность быстро обновлять панель.
 """

    _BUCKET_WINDOW = 60.0
    _FLOOD_INTERVAL = 0.4

    def __init__(self, settings: Settings, *, clock: Clock | None = None) -> None:
        self.settings = settings
        self._clock = clock or time.monotonic
        self._buckets: dict[int, deque[float]] = defaultdict(deque)
        self._last_seen: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        target = _unwrap_event(event)
        user_id = _user_id(target)
        if user_id is None or self.settings.is_admin(user_id):
            return await handler(event, data)

        now = self._clock()
        if self._is_flooding(user_id, now):
            await _notify_throttled(target)
            return None

        if _is_buy_action(target) and self._exceeds_buy_quota(user_id, now):
            await _notify_throttled(target)
            return None

        return await handler(event, data)

    def _is_flooding(self, user_id: int, now: float) -> bool:
        last = self._last_seen.get(user_id)
        if last is not None and now - last < self._FLOOD_INTERVAL:
            return True
        self._last_seen[user_id] = now
        return False

    def _exceeds_buy_quota(self, user_id: int, now: float) -> bool:
        bucket = self._buckets[user_id]
        cutoff = now - self._BUCKET_WINDOW
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= self.settings.throttle_buy_per_minute:
            return True
        bucket.append(now)
        return False


def _unwrap_event(event: TelegramObject) -> TelegramObject:
    """Updates wrap the real payload — peel one layer so we can inspect it."""
    if isinstance(event, Update):
        for attr in ("callback_query", "message"):
            inner = getattr(event, attr, None)
            if inner is not None:
                return inner
    return event


def _user_id(event: TelegramObject) -> int | None:
    user = getattr(event, "from_user", None)
    return user.id if user is not None else None


def _is_buy_action(event: TelegramObject) -> bool:
    data = getattr(event, "data", None)
    if not isinstance(data, str):
        return False
    for cb_type in (BuyPlan, BuyAsset, Invoice):
        try:
            cb_type.unpack(data)
            return True
        except (ValueError, TypeError):
            continue
    try:
        parsed = Menu.unpack(data)
        return parsed.action == "buy"
    except (ValueError, TypeError):
        return False


async def _notify_throttled(event: TelegramObject) -> None:
    if isinstance(event, CallbackQuery):
        await event.answer(texts.THROTTLED, show_alert=False)
    elif isinstance(event, Message):
        await event.answer(texts.THROTTLED)
