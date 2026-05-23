from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from ..database.session import SessionFactory, open_session


class DatabaseMiddleware(BaseMiddleware):
    """Открывает транзакционный сеанс для каждого обновления и вводит его как `сеанс`."""

    def __init__(self, factory: SessionFactory) -> None:
        self.factory = factory

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with open_session(self.factory) as session:
            data["session"] = session
            return await handler(event, data)
