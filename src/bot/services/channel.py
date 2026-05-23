from __future__ import annotations

from datetime import UTC, datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from ..logger import log


class ChannelService:
"""Завершает вызовы API Telegram, связанные с ограничением доступа к каналу."""

    def __init__(self, bot: Bot, channel_id: int) -> None:
        self.bot = bot
        self.channel_id = channel_id

    async def create_one_time_invite(
        self,
        *,
        expire_minutes: int = 60,
        name: str | None = None,
    ) -> str:
        expire_date = datetime.now(UTC) + timedelta(minutes=expire_minutes)
        link = await self.bot.create_chat_invite_link(
            chat_id=self.channel_id,
            name=name[:32] if name else None,
            expire_date=expire_date,
            member_limit=1,
            creates_join_request=False,
        )
        return link.invite_link

    async def remove_member(self, user_id: int) -> bool:
"""Забаньте, а затем разбаньте пользователя, не оставляя его в списке заблокированных.

 Возвращает `True`, когда пользователь был успешно удален (или изначально не был участником
), `False`, когда Telegram отклонил операцию — обычно из
-за того, что у бота нет необходимых разрешений в канале.
 """
        try:
            await self.bot.ban_chat_member(chat_id=self.channel_id, user_id=user_id)
            await self.bot.unban_chat_member(
                chat_id=self.channel_id, user_id=user_id, only_if_banned=True
            )
            return True
        except TelegramAPIError as exc:
            log.warning("channel.kick_failed", user_id=user_id, error=str(exc))
            return False
