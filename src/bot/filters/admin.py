from __future__ import annotations

from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message, TelegramObject

from ..config import Settings


class AdminFilter(Filter):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def __call__(self, event: TelegramObject) -> bool:
        user_id: int | None = None
        if (isinstance(event, Message) and event.from_user) or (isinstance(event, CallbackQuery) and event.from_user):
            user_id = event.from_user.id
        return user_id is not None and self.settings.is_admin(user_id)
