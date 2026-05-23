from __future__ import annotations

import contextlib

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ErrorEvent

from .. import texts
from ..logger import log

router = Router(name="errors")


@router.errors()
async def on_error(event: ErrorEvent) -> bool:
    exc = event.exception
    if isinstance(exc, TelegramBadRequest) and "сообщение не изменено" in str(exc):
        return True

    log.exception("handler.error", error=str(exc))

    update = event.update
    if update.callback_query is not None:
        with contextlib.suppress(Exception):
            await update.callback_query.answer(texts.GENERIC_ERROR, show_alert=False)
    elif update.message is not None:
        with contextlib.suppress(Exception):
            await update.message.answer(texts.GENERIC_ERROR)
    return True
